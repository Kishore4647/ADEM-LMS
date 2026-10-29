import { useState } from "react";
import { request } from "./api";
import { Form, nodePath, Panel, Table } from "./components";
import type { PageProps } from "./setup";

type Entry = { value: string; absent: boolean; manual: boolean };
export function RosterMarks({ data, user, refresh }: PageProps) {
  const [school, setSchool] = useState("");
  const [subject, setSubject] = useState("");
  const [session, setSession] = useState("");
  const [component, setComponent] = useState("assessment");
  const [period, setPeriod] = useState("");
  const [title, setTitle] = useState("");
  const [maximum, setMaximum] = useState("");
  const [draft, setDraft] = useState<Record<number, Entry>>({});
  const [message, setMessage] = useState("");
  const selectedSession = data.sessions.find((s) => s.id === +session);
  const subjects = data.nodes.filter(
    (n) =>
      n.level === "subject" &&
      (user.role === "super_admin" ||
        data.teaching.some(
          (t) => t.school_id === +school && t.subject_id === n.id,
        )),
  );
  const students = data.students.filter(
    (s) =>
      s.school_id === +school &&
      s.class_node_id === data.nodes.find((n) => n.id === +subject)?.parent_id,
  );
  function entry(studentId: number): Entry {
    if (draft[studentId]) return draft[studentId];
    const link = session
      ? data.attendance.find(
          (a) => a.session_id === +session && a.student_id === studentId,
        )
      : null;
    const existing = data.marks.find((m) =>
      link
        ? m.id === link.mark_id
        : m.student_id === studentId &&
          m.subject_node_id === +subject &&
          m.academic_period === period &&
          m.component === component &&
          (component === "quarterly_exam" || m.title === title),
    );
    return {
      value:
        existing?.obtained_marks === null ||
        existing?.obtained_marks === undefined
          ? ""
          : String(existing.obtained_marks),
      absent: existing?.is_absent ?? false,
      manual: link?.manual_present ?? false,
    };
  }
  function change(studentId: number, change: Partial<Entry>) {
    setDraft((old) => ({
      ...old,
      [studentId]: { ...entry(studentId), ...change },
    }));
    setMessage("");
  }
  function changeSession(value: string) {
    setSession(value);
    setDraft({});
    const current = data.sessions.find((s) => s.id === +value);
    if (current) {
      setSchool(String(current.school_id));
      setSubject(String(current.subject_id));
      setPeriod(current.period);
      setTitle(`Session #${current.id}`);
      setComponent("assessment");
    }
  }
  return (
    <Panel title="Class roster mark entry">
      <p>
        Enter marks for a full class and save together. Blank rows remain
        unrecorded; choose Absent explicitly. Existing records with the same
        student, subject, quarter and title are corrected on save.
      </p>
      <div className="mapping">
        <label>
          Session (optional)
          <select
            value={session}
            onChange={(e) => changeSession(e.target.value)}
          >
            <option value="">Independent assessment / activity / exam</option>
            {data.sessions.map((s) => (
              <option key={s.id} value={s.id}>
                #{s.id} · {s.session_date} ·{" "}
                {data.nodes.find((n) => n.id === s.subject_id)?.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          School
          <select
            value={school}
            disabled={!!session}
            onChange={(e) => {
              setSchool(e.target.value);
              setSubject("");
              setDraft({});
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
            disabled={!!session}
            onChange={(e) => {
              setSubject(e.target.value);
              setDraft({});
            }}
          >
            <option value="">Select subject</option>
            {subjects.map((n) => (
              <option key={n.id} value={n.id}>
                {nodePath(data.nodes, n.id)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Component
          <select
            value={component}
            disabled={!!session}
            onChange={(e) => {
              setComponent(e.target.value);
              setDraft({});
              if (e.target.value === "quarterly_exam") setMaximum("80");
            }}
          >
            <option value="assessment">Assessment</option>
            <option value="activity">Activity sheet</option>
            <option value="quarterly_exam">Quarterly examination /80</option>
          </select>
        </label>
        <label>
          Academic year / quarter
          <input
            value={period}
            readOnly={!!session}
            onChange={(e) => {
              setPeriod(e.target.value);
              setDraft({});
            }}
            placeholder="2026-Q1"
          />
        </label>
        <label>
          Assessment title
          <input
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setDraft({});
            }}
            placeholder="Assessment name"
          />
        </label>
        <label>
          Maximum marks
          <input
            type="number"
            min="0.01"
            step="any"
            value={component === "quarterly_exam" ? "80" : maximum}
            readOnly={component === "quarterly_exam"}
            onChange={(e) => setMaximum(e.target.value)}
          />
        </label>
      </div>
      <Table
        headers={[
          "Student",
          "Obtained marks",
          "Absent",
          ...(session ? ["Manual attendance"] : []),
        ]}
        rows={students.map((s) => {
          const value = entry(s.id);
          return [
            s.name,
            <input
              key="mark"
              aria-label={`Mark for ${s.name}`}
              type="number"
              min="0"
              step="any"
              disabled={value.absent}
              value={value.value}
              onChange={(e) => change(s.id, { value: e.target.value })}
            />,
            <input
              key="absent"
              aria-label={`Absent ${s.name}`}
              type="checkbox"
              checked={value.absent}
              onChange={(e) =>
                change(s.id, {
                  absent: e.target.checked,
                  value: e.target.checked ? "" : value.value,
                })
              }
            />,
            ...(session
              ? [
                  <input
                    key="manual"
                    aria-label={`Manual present ${s.name}`}
                    type="checkbox"
                    checked={value.manual}
                    onChange={(e) => change(s.id, { manual: e.target.checked })}
                  />,
                ]
              : []),
          ];
        })}
      />
      <Form
        fields={[]}
        label="Save class marks"
        submit={async () => {
          if (!school || !subject || !period || !title || !students.length)
            throw Error(
              "Select school/subject and enter the quarter and assessment title.",
            );
          const max = component === "quarterly_exam" ? 80 : Number(maximum);
          if (!Number.isFinite(max) || max <= 0)
            throw Error("Enter maximum marks.");
          const marks = students
            .filter((s) => entry(s.id).absent || entry(s.id).value !== "")
            .map((s) => {
              const value = entry(s.id);
              return {
                student_id: s.id,
                subject_node_id: +subject,
                component,
                academic_period: period,
                title,
                obtained_marks: value.absent ? null : Number(value.value),
                maximum_marks: max,
                is_absent: value.absent,
                session_id: selectedSession?.id ?? null,
                manual_present: value.manual,
              };
            });
          if (!marks.length)
            throw Error("Enter at least one mark or mark a student Absent.");
          const response = await request<{ saved: number }>(
            "workspace/marks/batch",
            { marks },
          );
          setMessage(
            `Saved ${response.saved} student record(s). Blank rows were left unrecorded.`,
          );
          setDraft({});
          await refresh();
        }}
      />
      {message && <p className="success">{message}</p>}
    </Panel>
  );
}
