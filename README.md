# ADEM LMS Phase 1

React and TypeScript frontend, FastAPI backend, Supabase PostgreSQL, Google OpenID Connect sign-in, and embedded Google Drive video playback.

## Run locally

Keep private credentials in the root `.env`. Use `.env.example` for variable names. Never commit OAuth credentials, database passwords, or secret API keys.

After installing dependencies once, run `./Start-Local.ps1` from the project root to start both local services. It reuses running services and reports readiness. The commands below cover first-time installation or manual starts.

PowerShell backend:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Open **http://localhost:5173**. Use `localhost`, consistently, for the frontend and OAuth callback, rather than mixing it with `127.0.0.1`. The callback registered in Google Cloud must match `GOOGLE_REDIRECT_URI`, normally `http://localhost:8000/api/auth/google/callback`.

Only the configured `BOOTSTRAP_ADMIN_EMAIL` can create the initial Super Admin on first Google sign-in. That admin provisions all other accounts by email. A matching Google account does not grant access without provisioning. Google identity claims are verified; school/class/subject permissions are checked separately by the API.

## Connected workflows

* Super Admin: schools, user provisioning and activation, school access, student enrolment, IST teaching assignments, curriculum, resources, session review, marks and corrections, attendance, assessments, quarterly publication, imports, analytics, community settings, audit history.
* Content Uploader: curriculum, private file upload, Drive video mapping, supplementary resources, structured DOCX import, rich question editing, scoring policy configuration, dispatch to enrolled students, results and school analytics, CSV/XLSX marks import.
* IST: assigned subjects and class rosters, resource access and supplementary uploads, media-readiness confirmation, missing-content reports, daily sessions and coverage, submission and rejection correction (notes, date and covered sub-topics), marks and attendance, online result visibility and quarterly calculations.
* School Management: school-scoped sessions, mark records, attendance, MCQ results, curriculum coverage, analytics, and published progress cards.
* Student: assigned resources, Google Drive player, MCQs with hints, submission and explanations, configurable retakes, gradebook, own progress cards, and permitted weekly practice leaderboard.

There are no demo accounts, fabricated marks, or seeded school/student records in the live database. Setup starts with schools, curriculum and user provisioning. Enrol student accounts and assign ISTs before dispatching assessments or recording sessions.

## Academic rules

* Quarterly subject result = examination /80 + converted classroom assessment /10 + converted activity sheet /10.
* Conversion = sum of present obtained marks / sum of present maximum marks ×10. Absent items are excluded, as confirmed by the client. All-absent or missing components remain pending, rather than becoming zero. Decimal rounding uses two places and ROUND_HALF_UP.
* Numeric zero is a real mark. A session assessment mark (including zero) gives Present; a blank/Absent mark gives Absent. Manual attendance cannot override official attendance. Assessment and activity maximums may vary, including classroom session assessments. An unrecorded session mark defaults to an absent record with nominal maximum 10, which is excluded from conversion; authorised mark entry can set the actual maximum.
* Each subject has one quarterly examination result per period. Update existing marks through correction rather than adding another examination.
* Session submission creates explicit Absent records for enrolled students without a saved session mark. It does not generate AI questions; Phase 1 uses uploaded Word questions.
* Marks remain editable by authorised ISTs. Corrections record before/after values in audit history. Changed marks flag published cards for republication; stale cards cannot be downloaded as current.
* ISTs can use the class roster grid to enter marks in one batch. Blank rows stay unrecorded; Absent is explicit. A batch is transactional: an invalid student/subject/mark prevents the entire batch from committing. Repeat saves correct the same student/subject/component/period/title record rather than adding duplicates.
* MCQ scores remain separate from classroom attendance and internal marks. Content Uploaders explicitly configure correct-answer marks, incorrect-answer penalty, attempt count, and counted attempt (first/latest/best). Unanswered questions score zero. Negative totals are preserved if a penalty produces one.
* Only Super Admin can correct a submitted MCQ attempt score, with a required reason. The original score is preserved and the configured first/latest/best result is recalculated; corrections never become classroom marks.
* Hints appear with questions; explanations appear after submission. Correct-answer keys are withheld from student API responses until attempts are exhausted. Retakes can see prior explanations by the client's requested explanation visibility policy.

## Word MCQ import

Upload `.docx`, not binary `.doc`. Required format:

```text
[Lesson] Arithmetic Expressions
[Sub-Topic] Evaluating Expressions
[Type]0
[Marks]1
[Negative Marks]0
Q.1) What is 2 + 2?
[a] a) 1
[b] b) 2
[c] c) 3
*[d] d) 4
[S1] Adding two and two produces four.
[Hint] Count two pairs.
```

Variable question count is supported. Four options, one `*` correct answer, hint, explanation, lesson and sub-topic are required. Type/Marks/Negative Marks are stored as source content but do not determine scoring. Choose school and Class → Subject → Chapter → Topic → Sub-topic, plus Easy/Medium/Hard.

Embedded PNG/JPEG/GIF/WebP images, Word tables and common native OMML equations (fractions, superscripts/subscripts, roots) render in the preview. Word shapes, SmartArt, legacy OLE equations, EMF/WMF images and complex equation layout require conversion to embedded PNG/JPEG first. Import rejects unsupported objects with an explicit error instead of losing them. Content Uploaders must visually review complex content. Word-specific advanced layout fidelity is not guaranteed.

Of the 15 `_e/_m/_h` sample documents, 13 validate. `NC080501_e.docx` question 5 lacks a starred correct answer. `NC080501_m.docx` question 3 has `d]d)` instead of `[d]d)`. Correct these in the source Word files and upload again. The originals have not been changed.

## Private files and Google Drive

Videos stay in Google Drive; the app stores the Drive file ID and curriculum association. Files must have restricted Google permissions for the intended accounts; pasting a link does not automatically share the Drive file. LMS login does not grant Drive access. The browser must also have an authorised Google session for playback. Google may expose its own player controls and URL through the browser; this solution cannot guarantee that links cannot be discovered, direct Drive viewing cannot occur, or screen recording is impossible.

Other files (Word originals, PDFs, images and CSV/XLSX sources) currently use **private backend disk storage**, behind authenticated file endpoints. This is deliberate for a runnable local build: Drive upload automation needs additional Google Drive consent/credentials that have not been configured. Source files remain downloadable to authorised staff. Extracted small images are stored inside question HTML; videos and original files are not stored as database blobs.

`UPLOADS_DIR` selects a persistent storage location. Back it up along with PostgreSQL. Docker Compose mounts a named volume. Do not deploy this disk adapter on ephemeral serverless storage. A managed Drive/Supabase Storage adapter can replace this file store without changing the LMS records, but has not been configured or tested against the client's external account.

## External mark imports

CSV/XLSX headers: `student_email,subject_id,component,academic_period,title,marks,maximum,absent`.

Match exact provisioned student email and numeric subject ID. Components are `assessment`, `activity`, `quarterly_exam`. An absent row has blank marks and `true` in absent. Upload first, validate, inspect errors/unmatched records, then confirm import of valid rows. Processing is idempotent per import job; summaries distinguish successful, failed and skipped rows. Existing exam records cannot be overwritten through imports. Legacy XLS is not accepted; save as XLSX.

## Migrations and security

Alembic tracks the initial database schema. Development startup upgrades to the latest revision. The initial revision safely adopts existing development tables and enables Row Level Security on LMS tables in PostgreSQL; no anonymous REST policies are created. FastAPI connects using the private backend database credentials. Do not use a browser database connection or expose Supabase secret keys.

Production migration command:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Future model changes require explicit migration revisions; `create_all` is not an alteration migration. Baseline downgrade is intentionally disabled to preserve academic data.

Session cookies are HttpOnly, SameSite=Lax, eight-hour signed sessions. Production sets Secure cookies and requires a dedicated `SESSION_SECRET`. The session contains only the user ID; role and active status are rechecked in the database. Origin validation protects all modifying endpoints. The Google client secret stays on the backend. A supplied `.env` session secret is preferred even in development; local fallback derives a signing key from the existing OAuth secret.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
npx playwright install chromium
npx playwright test
```

Backend tests use isolated SQLite fixtures, never real student records. They cover role and school access, zero/blank marks, absence exclusion, rounding, report rejection and resubmission, quarterly publication, MCQ privacy/scoring/attempt limits, strict sample Word imports, and origin validation. Browser tests exercise every role's navigation and the student attempt screen using mocked API fixtures. These complement the API tests; they do not constitute a live Google Drive integration test or production load test.

## Deployment

Dockerfiles and `compose.yaml` are included. Configure `.env` for the deployed HTTPS origin, Google callback and database. Build frontend with an empty `VITE_API_BASE_URL` when using the Nginx same-origin `/api` proxy. Run migrations before starting production. Set `ENVIRONMENT=production`, a random `SESSION_SECRET`, and persistent `UPLOADS_DIR`. Terminate HTTPS at the host/reverse proxy. For local Docker testing on port 8080, use development cookies, `FRONTEND_ORIGIN=http://localhost:8080`, and the matching Google callback URL through the proxy.

Supabase hosting capacity, backup restoration, production domains, Google OAuth publishing/test-user eligibility, Drive permissions, signed-off progress-card branding, and school acceptance testing must be checked before a public launch. WhatsApp integration and AI question generation are excluded from Phase 1 by client decision.
