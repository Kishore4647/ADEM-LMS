import { useCallback, useEffect, useState } from "react";
import { API, request, roleName } from "./api";
import type { Data, User } from "./api";
import { Badge, Empty, Form, Panel, Table } from "./components";
import { Curriculum, Enrolment, Resources, Schools, Users } from "./setup";
import type { PageProps } from "./setup";
import { Analytics, Attendance, Marks, Progress, Sessions } from "./academic";
import { Assessments } from "./assessments";
import { Community } from "./community";
import "./App.css";

const navigation: Record<string, string[]> = {
  super_admin: [
    "Overview",
    "Schools",
    "Users",
    "Enrolment",
    "Curriculum",
    "Resources",
    "Sessions",
    "Marks",
    "Attendance",
    "Assessments",
    "Progress",
    "Analytics",
    "Imports",
    "Audit",
    "Community",
  ],
  content_uploader: [
    "Overview",
    "Curriculum",
    "Resources",
    "Assessments",
    "Analytics",
    "Imports",
  ],
  ist: [
    "Overview",
    "Enrolment",
    "Resources",
    "Sessions",
    "Marks",
    "Attendance",
    "Assessments",
    "Progress",
  ],
  school_management: [
    "Overview",
    "Enrolment",
    "Analytics",
    "Sessions",
    "Marks",
    "Attendance",
    "Assessments",
    "Progress",
  ],
  student: [
    "Overview",
    "Resources",
    "Assessments",
    "Marks",
    "Progress",
    "Community",
  ],
};
const descriptions: Record<string, string> = {
  Overview: "Your learning community at a glance.",
  Schools: "Manage partner institutions.",
  Users: "Provision accounts and control school access.",
  Enrolment: "Connect students and trainers to schools and classes.",
  Curriculum: "Build the ordered academic structure.",
  Resources: "Organise learning materials and classroom videos.",
  Sessions: "Record classroom coverage and review session reports.",
  Marks: "Enter, review, and correct academic marks.",
  Attendance: "Official attendance from classroom assessment records.",
  Assessments: "Import, review, assign, and attempt online MCQs.",
  Progress: "Quarterly 80 + 10 + 10 results and published cards.",
  Analytics: "Academic performance within your authorised scope.",
  Imports: "Validate external marks before importing.",
  Audit: "History of academic and administrative actions.",
  Community:
    "Weekly online practice rankings and approved Hall of Fame entries.",
};

function Overview({
  data,
  user,
  go,
}: PageProps & { go: (page: string) => void }) {
  const stats =
    user.role === "student"
      ? [
          ["Learning resources", data.assets.length],
          ["Assigned MCQs", data.assignments.length],
          [
            "Completed MCQs",
            data.assignments.filter((a) => a.submitted_at).length,
          ],
          ["Progress cards", data.publications.filter((p) => !p.stale).length],
        ]
      : [
          ["Schools", data.schools.length],
          ["Students", data.students.length],
          ["Learning resources", data.assets.length],
          ["Session reports", data.sessions.length],
        ];
  return (
    <>
      <section className="welcome">
        <div>
          <span className="eyebrow">ADEM classroom</span>
          <h2>Welcome, {user.full_name?.split(" ")[0] || user.email}</h2>
          <p>Your records and learning activities stay connected here.</p>
        </div>
        <span className="welcome-mark" aria-hidden="true">
          A
        </span>
      </section>
      <div className="stats">
        {stats.map(([label, value]) => (
          <article key={String(label)}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <div className="two-column">
        <Panel title="Your workspace">
          <div className="shortcut-grid">
            {navigation[user.role]
              .filter((n) => n !== "Overview")
              .slice(0, 8)
              .map((n) => (
                <button key={n} onClick={() => go(n)}>
                  <b>
                    {n === "Marks" && user.role === "student"
                      ? "My gradebook"
                      : n}
                  </b>
                  <small>{descriptions[n]}</small>
                  <span aria-hidden="true">↗</span>
                </button>
              ))}
          </div>
        </Panel>
        <Panel title="Needs attention">
          {user.role === "student" ? (
            <>
              <p>
                {data.assignments.filter((a) => !a.submitted_at).length}{" "}
                assessments awaiting your first submission.
              </p>
              <p>
                {data.publications.filter((p) => p.stale).length} progress cards
                awaiting republication.
              </p>
            </>
          ) : (
            <>
              <p>
                {
                  data.sessions.filter((s) =>
                    ["submitted", "resubmitted"].includes(s.status),
                  ).length
                }{" "}
                reports awaiting review.
              </p>
              <p>
                {data.sessions.filter((s) => s.status === "rejected").length}{" "}
                reports need corrections.
              </p>
              <p>
                {data.assets.filter((a) => a.issue).length} learning resources
                have reported issues.
              </p>
              <p>
                {data.question_sets.filter((q) => q.status === "draft").length}{" "}
                MCQ drafts awaiting review.
              </p>
            </>
          )}
          {!data.schools.length && (
            <Empty>Ask your Super Admin to assign school access.</Empty>
          )}
        </Panel>
      </div>
    </>
  );
}

type ImportJob = {
  id: number;
  status: string;
  summary: Record<string, number>;
  rows: { row: number; status: string; student?: string; error?: string }[];
};
function Imports({ refresh, act }: PageProps) {
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<ImportJob | null>(null);
  const load = useCallback(
    async () => setJobs(await request<ImportJob[]>("workspace/imports")),
    [],
  );
  useEffect(() => {
    void load().catch(() => undefined);
  }, [load]);
  return (
    <>
      <Panel title="External examination marks">
        <p>CSV/XLSX column names:</p>
        <code className="schema">
          student_email, subject_id, component, academic_period, title, marks,
          maximum, absent
        </code>
        <p>
          Components: assessment, activity, quarterly_exam. Quarterly
          examination maximum must be 80. Match students by their provisioned
          Google email; find subject IDs in Curriculum. For absent rows, leave
          marks blank and use true in absent.
        </p>
        <a
          download="marks-template.csv"
          href="data:text/csv;charset=utf-8,student_email%2Csubject_id%2Ccomponent%2Cacademic_period%2Ctitle%2Cmarks%2Cmaximum%2Cabsent%0A"
        >
          Download CSV template
        </a>
        <label className="file-input">
          CSV or XLSX
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <Form
          fields={[]}
          label="Validate and preview"
          submit={async () => {
            if (!file) throw Error("Select a file.");
            const body = new FormData();
            body.set("file", file);
            const source = await request<{ id: number }>(
              "workspace/files",
              body,
            );
            setSelected(
              await request<ImportJob>("workspace/imports/preview", {
                file_id: source.id,
              }),
            );
            await load();
          }}
        />
      </Panel>
      {selected && (
        <Panel title={`Import #${selected.id}`}>
          <p>
            {Object.entries(selected.summary)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ")}
          </p>
          <Table
            headers={["Row", "Student", "Status", "Details"]}
            rows={selected.rows.map((r) => [
              r.row,
              r.student,
              <Badge value={r.status} />,
              r.error,
            ])}
          />
          {selected.status === "validated" && (
            <button
              className="primary"
              onClick={() =>
                act(async () => {
                  setSelected(
                    await request<ImportJob>(
                      `workspace/imports/${selected.id}/commit`,
                      {},
                    ),
                  );
                  await load();
                  await refresh();
                })
              }
            >
              Import valid rows
            </button>
          )}
        </Panel>
      )}
      <Panel title="Import history">
        <Table
          headers={["Job", "Status", "Summary", ""]}
          rows={jobs.map((j) => [
            j.id,
            j.status,
            JSON.stringify(j.summary),
            <button className="secondary" onClick={() => setSelected(j)}>
              View
            </button>,
          ])}
        />
      </Panel>
    </>
  );
}

function Audit() {
  const [rows, setRows] = useState<
    {
      id: number;
      actor_id: number;
      action: string;
      entity: string;
      entity_id: number;
      created_at: string;
      detail: object;
    }[]
  >([]);
  const [error, setError] = useState("");
  useEffect(() => {
    request<typeof rows>("workspace/audit")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <Panel title="Recent audit history">
      {error && <p className="error">{error}</p>}
      <Table
        headers={["Time", "Actor", "Action", "Record", "Detail"]}
        rows={rows.map((r) => [
          new Date(r.created_at).toLocaleString(),
          `User #${r.actor_id}`,
          r.action,
          `${r.entity} #${r.entity_id}`,
          <details>
            <summary>Changes</summary>
            <pre>{JSON.stringify(r.detail, null, 2)}</pre>
          </details>,
        ])}
      />
    </Panel>
  );
}

function Login({ error }: { error: string }) {
  const [hall, setHall] = useState<{ name: string; class_name: string }[]>([]);
  useEffect(() => {
    request<typeof hall>("public/hall-of-fame")
      .then(setHall)
      .catch(() => undefined);
  }, []);
  return (
    <main className="login-page">
      <nav className="login-nav">
        <span className="brand">
          <span className="brand-mark">A</span>ADEM <small>LMS</small>
        </span>
        <span className="login-tag">A connected classroom</span>
      </nav>
      <div className="login-layout">
        <section>
          <span className="eyebrow">Learn. Practise. Progress.</span>
          <h1>
            Every classroom.
            <br />
            One learning journey.
          </h1>
          <p>
            Curriculum, classroom learning, assessments, and progress brought
            together for your school.
          </p>
          <div className="login-points">
            <span>01 &nbsp; Structured learning</span>
            <span>02 &nbsp; Meaningful assessment</span>
            <span>03 &nbsp; Visible progress</span>
          </div>
        </section>
        <section className="login-card">
          <div className="login-symbol">A</div>
          <h2>Welcome to ADEM LMS</h2>
          <p>
            Sign in with your authorised Google account to open your workspace.
          </p>
          <a className="google-button" href={`${API}/api/auth/google/login`}>
            <span>G</span>Continue with Google
          </a>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <small>Your school administrator manages account access.</small>
        </section>
      </div>
      {hall.length > 0 && (
        <section className="public-hall">
          <h2>Hall of Fame</h2>
          <div>
            {hall.map((entry, i) => (
              <article key={i}>
                <span>★</span>
                <h3>{entry.name}</h3>
                <p>{entry.class_name}</p>
              </article>
            ))}
          </div>
        </section>
      )}
      <footer>ADEM Learning Management System</footer>
    </main>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState("Overview");
  const [menu, setMenu] = useState(false);
  const refresh = useCallback(
    async () => setData(await request<Data>("workspace/data")),
    [],
  );
  useEffect(() => {
    request<User>("auth/me")
      .then(async (current) => {
        setUser(current);
        await refresh();
      })
      .catch((e) => {
        if (!e.message.includes("Authentication required")) setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [refresh]);
  async function act(action: () => Promise<unknown>) {
    setError("");
    setNotice("");
    try {
      await action();
      setNotice("Action completed successfully.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function logout() {
    await act(async () => {
      await request("auth/logout", {});
      setUser(null);
      setData(null);
      history.replaceState(null, "", "/");
    });
  }
  if (loading)
    return (
      <main className="loading">
        <span className="brand-mark">A</span>
        <p>Opening your workspace…</p>
      </main>
    );
  const oauthError = new URLSearchParams(location.search).get("error");
  if (!user)
    return (
      <Login
        error={
          error ||
          (oauthError
            ? "Sign-in failed or this Google account is not authorised. Please contact your administrator."
            : "")
        }
      />
    );
  if (!data)
    return (
      <main className="loading">
        <p className="error">{error || "Unable to load your workspace."}</p>
        <button onClick={() => act(refresh)}>Retry</button>
        <button onClick={logout}>Sign out</button>
      </main>
    );
  const props = { data, user, refresh, act };
  const pages: Record<string, React.ReactNode> = {
    Overview: <Overview {...props} go={setPage} />,
    Schools: <Schools {...props} />,
    Users: <Users {...props} />,
    Enrolment: <Enrolment {...props} />,
    Curriculum: <Curriculum {...props} />,
    Resources: <Resources {...props} />,
    Sessions: <Sessions {...props} />,
    Marks: <Marks {...props} />,
    Attendance: <Attendance {...props} />,
    Assessments: <Assessments {...props} />,
    Progress: <Progress {...props} />,
    Analytics: <Analytics {...props} />,
    Imports: <Imports {...props} />,
    Audit: <Audit />,
    Community: <Community {...props} />,
  };
  return (
    <div className={`app-shell ${menu ? "menu-open" : ""}`}>
      <aside className="sidebar">
        <a className="brand" href="#" onClick={() => setPage("Overview")}>
          <span className="brand-mark">A</span>ADEM <small>LMS</small>
        </a>
        <span className="workspace-label">{roleName(user.role)} workspace</span>
        <nav>
          {navigation[user.role]?.map((name, i) => (
            <button
              key={name}
              className={page === name ? "nav-item active" : "nav-item"}
              onClick={() => {
                setPage(name);
                setMenu(false);
                setError("");
                setNotice("");
              }}
            >
              <span className="nav-icon" aria-hidden="true">
                {
                  [
                    "◫",
                    "▦",
                    "◎",
                    "↗",
                    "≡",
                    "▷",
                    "▤",
                    "✎",
                    "✓",
                    "◇",
                    "◷",
                    "▥",
                    "⇧",
                    "↺",
                  ][i]
                }
              </span>
              {name === "Marks" && user.role === "student"
                ? "My gradebook"
                : name}
            </button>
          ))}
        </nav>
        <div className="account">
          <span className="avatar">
            {(user.full_name || user.email)[0].toUpperCase()}
          </span>
          <div>
            <b>{user.full_name || user.email}</b>
            <small>{user.email}</small>
            <button onClick={logout}>Sign out</button>
          </div>
        </div>
      </aside>
      <div className="main-area">
        <header className="app-topbar">
          <button
            className="menu-toggle"
            aria-label="Toggle navigation"
            onClick={() => setMenu(!menu)}
          >
            ☰
          </button>
          <span>
            ADEM / <b>{page}</b>
          </span>
          <div className="topbar-actions">
            <button className="link" onClick={() => act(refresh)}>
              Refresh data
            </button>
            <Badge value={roleName(user.role)} />
          </div>
        </header>
        <main className="workspace">
          <header className="page-header">
            <div>
              <span className="eyebrow">Learning workspace</span>
              <h1>
                {page === "Marks" && user.role === "student"
                  ? "My gradebook"
                  : page}
              </h1>
              <p>{descriptions[page]}</p>
            </div>
          </header>
          {error && (
            <div className="error banner" role="alert">
              {error}
              <button onClick={() => setError("")}>×</button>
            </div>
          )}
          {notice && (
            <div className="success banner" role="status">
              {notice}
              <button onClick={() => setNotice("")}>×</button>
            </div>
          )}
          {pages[page]}
        </main>
      </div>
    </div>
  );
}
