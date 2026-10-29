import { useState } from "react";
import { API, request, roleName } from "./api";
import type { Mark, Result } from "./api";
import { Badge, Form, nodePath, Panel, Table } from "./components";
import type { PageProps } from "./setup";
import { RosterMarks } from "./roster";

export function Sessions({ data, user, refresh, act }: PageProps) {
  const [school, setSchool] = useState("");
  const [subject, setSubject] = useState("");
  const [subtopics, setSubtopics] = useState<number[]>([]);
  const [review, setReview] = useState<number | null>(null);
  const [edit, setEdit] = useState<number | null>(null);
  const [editTopics, setEditTopics] = useState<number[]>([]);
  const allowedSubjects = data.nodes.filter(
    (n) =>
      n.level === "subject" &&
      (user.role === "super_admin" ||
        data.teaching.some(
          (a) => a.school_id === +school && a.subject_id === n.id,
        )),
  );
  const descendant = (id: number, subjectId = +subject): boolean => {
    const node = data.nodes.find((n) => n.id === id);
    return (
      node?.parent_id === subjectId ||
      (!!node?.parent_id && descendant(node.parent_id, subjectId))
    );
  };
  return (
    <>
      {["ist", "super_admin"].includes(user.role) && (
        <Panel title="Record classroom session">
          <div className="mapping">
            <label>
              School
              <select
                value={school}
                onChange={(e) => {
                  setSchool(e.target.value);
                  setSubject("");
                  setSubtopics([]);
                }}
              >
                <option value="">Select school</option>
                {data.schools.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Subject
              <select
                value={subject}
                onChange={(e) => {
                  setSubject(e.target.value);
                  setSubtopics([]);
                }}
              >
                <option value="">Select subject</option>
                {allowedSubjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {nodePath(data.nodes, s.id)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <fieldset>
            <legend>Sub-topics covered</legend>
            {data.nodes
              .filter(
                (n) => n.level === "sub_topic" && subject && descendant(n.id),
              )
              .map((n) => (
                <label className="check" key={n.id}>
                  <input
                    type="checkbox"
                    checked={subtopics.includes(n.id)}
                    onChange={(e) =>
                      setSubtopics(
                        e.target.checked
                          ? [...subtopics, n.id]
                          : subtopics.filter((id) => id !== n.id),
                      )
                    }
                  />
                  {nodePath(data.nodes, n.id)}
                </label>
              ))}
          </fieldset>
          <Form
            fields={[
              { key: "session_date", label: "Session date", type: "date" },
              {
                key: "period",
                label: "Academic year / quarter (e.g. 2026-Q1)",
              },
              {
                key: "notes",
                label: "Session notes",
                type: "textarea",
                required: false,
              },
            ]}
            submit={async (v) => {
              await request("workspace/sessions", {
                ...v,
                school_id: +school,
                subject_id: +subject,
                subtopic_ids: subtopics,
              });
              await refresh();
            }}
            label="Save draft session"
          />
        </Panel>
      )}
      <Panel title="Daily session reports">
        <Table
          headers={["Session", "Coverage", "Review", "Actions"]}
          rows={data.sessions.map((s) => [
            <>
              <b>
                #{s.id} · {s.session_date}
              </b>
              <small>
                {data.schools.find((x) => x.id === s.school_id)?.name} ·{" "}
                {s.period}
              </small>
            </>,
            <>
              {nodePath(data.nodes, s.subject_id)}
              <small>
                {s.subtopic_ids
                  .map((id) => data.nodes.find((n) => n.id === id)?.name)
                  .join(", ")}
              </small>
              <p>{s.notes}</p>
            </>,
            <>
              <Badge value={s.status} />
              <small>{s.review_comment}</small>
            </>,
            <div className="actions">
              {["draft", "rejected"].includes(s.status) &&
                ["ist", "super_admin"].includes(user.role) && (
                  <>
                    <button
                      className="primary"
                      onClick={() =>
                        act(async () => {
                          await request(
                            `workspace/sessions/${s.id}/submit`,
                            {},
                          );
                          await refresh();
                        })
                      }
                    >
                      {s.status === "rejected" ? "Resubmit" : "Submit"}
                    </button>
                    <button
                      className="secondary"
                      onClick={() => {
                        setEdit(s.id);
                        setEditTopics(s.subtopic_ids);
                      }}
                    >
                      Edit report
                    </button>
                  </>
                )}
              {user.role === "super_admin" &&
                ["submitted", "resubmitted"].includes(s.status) && (
                  <button className="primary" onClick={() => setReview(s.id)}>
                    Review
                  </button>
                )}
            </div>,
          ])}
        />
      </Panel>
      {edit && (
        <Panel title={`Correct session #${edit}`}>
          <fieldset>
            <legend>Correct sub-topics covered</legend>
            {data.nodes
              .filter(
                (n) =>
                  n.level === "sub_topic" &&
                  descendant(
                    n.id,
                    data.sessions.find((s) => s.id === edit)?.subject_id,
                  ),
              )
              .map((n) => (
                <label key={n.id} className="check">
                  <input
                    type="checkbox"
                    checked={editTopics.includes(n.id)}
                    onChange={(e) =>
                      setEditTopics(
                        e.target.checked
                          ? [...editTopics, n.id]
                          : editTopics.filter((id) => id !== n.id),
                      )
                    }
                  />
                  {nodePath(data.nodes, n.id)}
                </label>
              ))}
          </fieldset>
          <Form
            initial={{
              notes: data.sessions.find((s) => s.id === edit)?.notes ?? "",
              session_date:
                data.sessions.find((s) => s.id === edit)?.session_date ?? "",
            }}
            fields={[
              {
                key: "session_date",
                label: "Correct session date",
                type: "date",
              },
              {
                key: "notes",
                label: "Session notes",
                type: "textarea",
                required: false,
              },
            ]}
            submit={async (v) => {
              await request(
                `workspace/sessions/${edit}`,
                { ...v, subtopic_ids: editTopics },
                "PATCH",
              );
              setEdit(null);
              await refresh();
            }}
          />
        </Panel>
      )}
      {review && (
        <Panel title={`Review session #${review}`}>
          <Form
            fields={[
              {
                key: "status",
                label: "Decision",
                options: [
                  { id: "approved", name: "Approve" },
                  { id: "rejected", name: "Reject" },
                ],
              },
              {
                key: "comment",
                label: "Review comments (required for rejection)",
                type: "textarea",
                required: false,
              },
            ]}
            submit={async (v) => {
              await request(`workspace/sessions/${review}/review`, v);
              setReview(null);
              await refresh();
            }}
            label="Save decision"
          />
        </Panel>
      )}
    </>
  );
}

export function Marks({ data, user, refresh }: PageProps) {
  const [editing, setEditing] = useState<Mark | null>(null);
  const [component, setComponent] = useState("assessment");
  const [absent, setAbsent] = useState(false);
  const [session, setSession] = useState("");
  const [filter, setFilter] = useState("");
  const canEdit = ["ist", "super_admin"].includes(user.role);
  const currentSession = data.sessions.find((s) => s.id === +session);
  const subjects = data.nodes.filter(
    (n) =>
      n.level === "subject" &&
      (user.role === "super_admin" ||
        user.role !== "ist" ||
        data.teaching.some((a) => a.subject_id === n.id)),
  );
  const fields = [
    {
      key: "student_id",
      label: "Student",
      options: data.students
        .filter(
          (s) =>
            !currentSession ||
            (s.school_id === currentSession.school_id &&
              s.class_node_id ===
                data.nodes.find((n) => n.id === currentSession.subject_id)
                  ?.parent_id),
        )
        .map((s) => ({ id: s.id, name: s.name })),
    },
    {
      key: "subject_node_id",
      label: "Subject",
      options: subjects
        .filter((n) => !currentSession || n.id === currentSession.subject_id)
        .map((n) => ({ id: n.id, name: nodePath(data.nodes, n.id) })),
    },
    {
      key: "academic_period",
      label: "Academic year / quarter",
      value: currentSession?.period,
    },
    {
      key: "title",
      label: "Assessment title",
      value: currentSession ? `Session #${currentSession.id}` : undefined,
    },
    ...(!absent
      ? [
          {
            key: "obtained_marks",
            label: "Obtained marks",
            type: "number",
            min: 0,
          },
        ]
      : []),
    {
      key: "maximum_marks",
      label: "Maximum marks",
      type: "number",
      min: 0.01,
      value:
        component === "quarterly_exam"
          ? "80"
          : currentSession
            ? "10"
            : undefined,
    },
    ...(currentSession
      ? [
          {
            key: "manual_present",
            label: "Manual attendance",
            options: [
              { id: "true", name: "Present" },
              { id: "false", name: "Absent" },
            ],
          },
        ]
      : []),
  ];
  const initial: Record<string, string> = editing
    ? Object.fromEntries(
        Object.entries(editing).map(([k, v]) => [
          k,
          v === null ? "" : String(v),
        ]),
      )
    : {};
  return (
    <>
      {canEdit && (
        <RosterMarks
          data={data}
          user={user}
          refresh={refresh}
          act={async (action) => {
            await action();
          }}
        />
      )}
      {canEdit && (
        <Panel
          title={
            editing
              ? `Correct mark #${editing.id}`
              : "Enter assessment / activity / exam marks"
          }
        >
          <div className="mapping">
            <label>
              Component
              <select
                value={component}
                disabled={!!editing}
                onChange={(e) => {
                  setComponent(e.target.value);
                  setSession("");
                }}
              >
                <option value="assessment">Classroom assessment → 10</option>
                <option value="activity">Activity sheet → 10</option>
                <option value="quarterly_exam">
                  Quarterly examination / 80
                </option>
              </select>
            </label>
            {component === "assessment" && (
              <label>
                Classroom session (optional)
                <select
                  value={session}
                  onChange={(e) => setSession(e.target.value)}
                >
                  <option value="">Independent assessment</option>
                  {data.sessions.map((s) => (
                    <option key={s.id} value={s.id}>
                      #{s.id} {s.session_date} ·{" "}
                      {data.nodes.find((n) => n.id === s.subject_id)?.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={absent}
              onChange={(e) => setAbsent(e.target.checked)}
            />
            Absent — excluded from the quarterly denominator
          </label>
          <Form
            key={`${editing?.id ?? "new"}-${component}-${session}-${absent}`}
            fields={fields}
            initial={initial}
            submit={async (v) => {
              await request(
                `workspace/marks${editing ? `/${editing.id}` : ""}`,
                {
                  student_id: +v.student_id,
                  subject_node_id: +v.subject_node_id,
                  component,
                  academic_period: v.academic_period,
                  title: v.title,
                  obtained_marks: absent ? null : +v.obtained_marks,
                  maximum_marks: +v.maximum_marks,
                  is_absent: absent,
                  session_id: session ? +session : null,
                  manual_present: v.manual_present === "true",
                },
                editing ? "PUT" : "POST",
              );
              setEditing(null);
              await refresh();
            }}
            label={editing ? "Save correction" : "Save mark"}
          />
          {editing && (
            <button
              className="link"
              onClick={() => {
                setEditing(null);
                setAbsent(false);
              }}
            >
              Cancel correction
            </button>
          )}
        </Panel>
      )}
      <Panel title={user.role === "student" ? "My gradebook" : "Mark records"}>
        <p>
          <a
            className="download"
            href={`${API}/api/workspace/exports/marks.csv`}
          >
            Export authorised marks as CSV
          </a>
        </p>
        <input
          aria-label="Filter marks"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by name, subject, period…"
        />
        <Table
          headers={[
            "Student / period",
            "Subject / component",
            "Assessment",
            "Mark",
            "",
          ]}
          rows={data.marks
            .filter((m) =>
              `${data.students.find((s) => s.id === m.student_id)?.name} ${nodePath(data.nodes, m.subject_node_id)} ${m.academic_period}`
                .toLowerCase()
                .includes(filter.toLowerCase()),
            )
            .map((m) => [
              <>
                {data.students.find((s) => s.id === m.student_id)?.name}
                <small>{m.academic_period}</small>
              </>,
              <>
                {nodePath(data.nodes, m.subject_node_id)}
                <small>{roleName(m.component)}</small>
              </>,
              m.title,
              m.is_absent ? (
                <Badge value="absent" />
              ) : (
                `${m.obtained_marks} / ${m.maximum_marks}`
              ),
              canEdit && (
                <button
                  className="secondary"
                  onClick={() => {
                    setEditing(m);
                    setComponent(m.component);
                    setAbsent(m.is_absent);
                    const link = data.attendance.find(
                      (a) => a.mark_id === m.id,
                    );
                    setSession(link ? String(link.session_id) : "");
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                >
                  Correct
                </button>
              ),
            ])}
        />
      </Panel>
    </>
  );
}

export function Attendance({ data }: PageProps) {
  return (
    <Panel title="Official session attendance">
      <p>
        Any saved numeric classroom mark, including zero, means Present. Blank
        marks mean Absent. Manual attendance is recorded separately.
      </p>
      <Table
        headers={["Student", "Session", "Manual", "Official"]}
        rows={data.attendance.map((a) => [
          data.students.find((s) => s.id === a.student_id)?.name,
          `#${a.session_id}`,
          a.manual_present ? "Present" : "Absent",
          <Badge value={a.final_status.toLowerCase()} />,
        ])}
      />
    </Panel>
  );
}

export function Progress({ data, user, refresh, act }: PageProps) {
  const [selection, setSelection] = useState<{
    student_id: number;
    subject_id: number;
    period: string;
  } | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  return (
    <>
      <Panel title="Quarterly calculation">
        <p>
          Assessment total ÷ assessment maximum × 10, plus activity total ÷
          activity maximum × 10, plus the subject examination out of 80. Absent
          items are excluded. Components are rounded to two decimals.
        </p>
        <Form
          fields={[
            {
              key: "student_id",
              label: "Student",
              options: data.students.map((s) => ({ id: s.id, name: s.name })),
            },
            {
              key: "subject_id",
              label: "Subject",
              options: data.nodes
                .filter((n) => n.level === "subject")
                .map((n) => ({ id: n.id, name: nodePath(data.nodes, n.id) })),
            },
            { key: "period", label: "Academic year / quarter" },
          ]}
          submit={async (v) => {
            const chosen = {
              student_id: +v.student_id,
              subject_id: +v.subject_id,
              period: v.period,
            };
            const query = new URLSearchParams(
              Object.entries(chosen).map(([k, value]) => [k, String(value)]),
            );
            setResult(await request<Result>(`workspace/results?${query}`));
            setSelection(chosen);
          }}
          label="Calculate"
        />
        {result && (
          <>
            <div className="stats">
              {[
                ["Assessment / 10", result.assessment],
                ["Activity / 10", result.activity],
                ["Examination / 80", result.exam],
                ["Total / 100", result.total],
              ].map(([label, value]) => (
                <article key={String(label)}>
                  <span>{label}</span>
                  <strong>{value ?? "Pending"}</strong>
                </article>
              ))}
            </div>
            {!result.complete && (
              <p className="muted">
                Missing marks or an entirely absent component must be resolved
                before publication.
              </p>
            )}
            {user.role === "super_admin" && (
              <button
                className="primary"
                disabled={!result.complete}
                onClick={() =>
                  act(async () => {
                    await request("workspace/progress/publish", selection);
                    await refresh();
                  })
                }
              >
                Publish / regenerate progress card
              </button>
            )}
          </>
        )}
      </Panel>
      <Panel title="Published progress cards">
        <Table
          headers={["Student", "Subject", "Quarter", "Total", "Download"]}
          rows={data.publications.map((p) => [
            data.students.find((s) => s.id === p.student_id)?.name,
            nodePath(data.nodes, p.subject_id),
            p.period,
            p.snapshot.total,
            p.stale ? (
              <Badge value="requires_republication" />
            ) : (
              <a
                className="download"
                href={`${API}/api/workspace/progress/${p.id}/pdf`}
                target="_blank"
                rel="noreferrer"
              >
                Download PDF
              </a>
            ),
          ])}
        />
      </Panel>
    </>
  );
}

export function Analytics({ data }: PageProps) {
  const [school, setSchool] = useState("");
  const students = data.students.filter(
    (s) => !school || s.school_id === +school,
  );
  const marks = data.marks.filter((m) =>
    students.some((s) => s.id === m.student_id),
  );
  const sessions = data.sessions.filter(
    (s) => !school || s.school_id === +school,
  );
  const coverage = new Set(
    sessions
      .filter((s) => s.status === "approved")
      .flatMap((s) => s.subtopic_ids),
  );
  return (
    <>
      <Panel title="Institution performance">
        <label>
          School
          <select value={school} onChange={(e) => setSchool(e.target.value)}>
            <option value="">All authorised schools</option>
            {data.schools.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <div className="stats">
          {[
            ["Students", students.length],
            ["Sessions", sessions.length],
            ["Sub-topics approved", coverage.size],
            [
              "Pending reports",
              sessions.filter((s) =>
                ["submitted", "resubmitted"].includes(s.status),
              ).length,
            ],
          ].map(([label, value]) => (
            <article key={String(label)}>
              <span>{label}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </div>
        <Table
          headers={[
            "Category",
            "Recorded",
            "Absent",
            "Average % (present only)",
          ]}
          rows={["assessment", "activity", "quarterly_exam"].map((c) => {
            const all = marks.filter((m) => m.component === c);
            const eligible = all.filter(
              (m) => !m.is_absent && m.obtained_marks !== null,
            );
            return [
              roleName(c),
              all.length,
              all.filter((m) => m.is_absent).length,
              eligible.length
                ? (
                    eligible.reduce(
                      (sum, m) =>
                        sum + (m.obtained_marks! / m.maximum_marks) * 100,
                      0,
                    ) / eligible.length
                  ).toFixed(2)
                : "—",
            ];
          })}
        />
        <h3>Curriculum coverage</h3>
        {data.nodes
          .filter(
            (n) =>
              n.level === "sub_topic" &&
              (!school || sessions.some((s) => s.subtopic_ids.includes(n.id))),
          )
          .map((n) => (
            <div className="coverage" key={n.id}>
              <span>{nodePath(data.nodes, n.id)}</span>
              <Badge value={coverage.has(n.id) ? "covered" : "pending"} />
            </div>
          ))}
      </Panel>
    </>
  );
}
