import { useState } from "react";
import { API, request } from "./api";
import type { Policy, Question, QuestionSet } from "./api";
import {
  Badge,
  Empty,
  Form,
  Mapping,
  nodePath,
  Panel,
  Rich,
  RichEditor,
  Table,
} from "./components";
import type { PageProps } from "./setup";

type Attempt = {
  id: number;
  title: string;
  questions: Question[];
  policy: Policy;
  attempts: number;
  remaining: boolean;
  score: number | null;
  explanations?: string[];
  history: { score: number; submitted_at: string }[];
};

export function Assessments({ data, user, refresh, act }: PageProps) {
  const [mapping, setMapping] = useState({ school_id: 0, subtopic_id: 0 });
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<QuestionSet | null>(null);
  const [test, setTest] = useState<Attempt | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [explanations, setExplanations] = useState<string[]>([]);
  const [score, setScore] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [taking, setTaking] = useState(false);
  const [correcting, setCorrecting] = useState<number | null>(null);
  const canManage = ["super_admin", "content_uploader"].includes(user.role);
  async function openAttempt(id: number) {
    const next = await request<Attempt>(`workspace/attempts/${id}`);
    setTest(next);
    let draft = Array(next.questions.length).fill(null);
    try {
      const saved = JSON.parse(
        sessionStorage.getItem(
          `adem-attempt-${user.id}-${next.id}-${next.attempts}`,
        ) ?? "null",
      );
      if (
        Array.isArray(saved) &&
        saved.length === draft.length &&
        saved.every(
          (v) => v === null || (Number.isInteger(v) && v >= 0 && v <= 3),
        )
      )
        draft = saved;
    } catch {
      /* Draft persistence is optional. */
    }
    setAnswers(draft);
    setTaking(next.attempts === 0 && next.remaining);
    setExplanations(next.explanations ?? []);
    setScore(next.score);
  }
  function choose(index: number, value: number) {
    const next = answers.map((a, i) => (i === index ? value : a));
    setAnswers(next);
    try {
      if (test)
        sessionStorage.setItem(
          `adem-attempt-${user.id}-${test.id}-${test.attempts}`,
          JSON.stringify(next),
        );
    } catch {
      /* Continue if browser storage is unavailable. */
    }
  }
  return (
    <>
      {canManage && (
        <Panel title="Import Word MCQ document">
          <p>
            Select school and the full curriculum path. Import creates a draft
            for review; no fixed question count is required.
          </p>
          <Mapping data={data} onChange={setMapping} />
          <label className="file-input">
            Word source (.docx)
            <input
              type="file"
              accept=".docx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <Form
            fields={[
              {
                key: "difficulty",
                label: "Difficulty",
                options: ["easy", "medium", "hard"].map((v) => ({
                  id: v,
                  name: v,
                })),
              },
            ]}
            submit={async (v) => {
              if (!file || !mapping.school_id || !mapping.subtopic_id)
                throw Error(
                  "Choose a Word document, school, and curriculum path.",
                );
              const upload = new FormData();
              upload.set("file", file);
              const source = await request<{ id: number }>(
                "workspace/files",
                upload,
              );
              const form = new FormData();
              form.set("file_id", String(source.id));
              form.set("school_id", String(mapping.school_id));
              form.set("subtopic_id", String(mapping.subtopic_id));
              form.set("difficulty", v.difficulty);
              const imported = await request<{ id: number }>(
                "workspace/question-sets/import",
                form,
              );
              await refresh();
              setSelected(
                await request<QuestionSet>(
                  `workspace/question-sets/${imported.id}`,
                ),
              );
            }}
            label="Import and validate"
          />
        </Panel>
      )}
      <Panel
        title={
          user.role === "student" ? "My online assessments" : "Question sets"
        }
      >
        <Table
          headers={[
            "Title",
            "Curriculum",
            "Questions / difficulty",
            "Status",
            "Actions",
          ]}
          rows={data.question_sets.map((q) => [
            q.title,
            nodePath(data.nodes, q.subtopic_id),
            `${q.question_count} / ${q.difficulty}`,
            <Badge value={q.status} />,
            <div className="actions">
              {canManage && (
                <>
                  <button
                    className="secondary"
                    onClick={() =>
                      act(async () =>
                        setSelected(
                          await request<QuestionSet>(
                            `workspace/question-sets/${q.id}`,
                          ),
                        ),
                      )
                    }
                  >
                    Review / edit
                  </button>
                  {q.source_file_id && (
                    <a
                      className="link"
                      href={`${API}/api/workspace/files/${q.source_file_id}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Word source
                    </a>
                  )}
                  <button
                    className="primary"
                    onClick={() =>
                      act(async () => {
                        await request(
                          `workspace/question-sets/${q.id}/dispatch`,
                          {},
                        );
                        await refresh();
                      })
                    }
                  >
                    {q.status === "draft"
                      ? "Dispatch"
                      : "Assign newly enrolled students"}
                  </button>
                </>
              )}
              {user.role === "student" &&
                data.assignments
                  .filter((a) => a.question_set_id === q.id)
                  .map((a) => (
                    <button
                      key={a.id}
                      className="primary"
                      onClick={() => act(() => openAttempt(a.id))}
                    >
                      {a.submitted_at ? "Results / retake" : "Attempt"}
                    </button>
                  ))}
            </div>,
          ])}
        />
      </Panel>
      {selected && (
        <QuestionEditor
          key={selected.id}
          item={selected}
          onClose={() => setSelected(null)}
          onSave={async (questions, policy, title, category) => {
            await request(
              `workspace/question-sets/${selected.id}`,
              { questions, policy, title, category },
              "PUT",
            );
            await refresh();
          }}
        />
      )}
      {test && (
        <Panel title={test.title}>
          <div className="actions">
            <Badge value={test.remaining ? "available" : "completed"} />
            <span>
              Attempts {test.attempts} / {test.policy.max_attempts}
            </span>
            <button className="link" onClick={() => setTest(null)}>
              Close
            </button>
          </div>
          <p>
            Correct: +{test.policy.correct_marks}, incorrect: −
            {test.policy.incorrect_penalty}, unanswered: 0. Counted attempt:{" "}
            {test.policy.counted_attempt}.
          </p>
          {score !== null && (
            <p className="result-banner">Counted score: {score}</p>
          )}
          {test.questions.map((q, index) => (
            <article className="question" key={index}>
              <h3>Question {index + 1}</h3>
              <Rich html={q.prompt} />
              <div className="hint">
                <b>Hint</b>
                <Rich html={q.hint} />
              </div>
              {q.options.map((option, i) => (
                <label className="answer" key={i}>
                  <input
                    type="radio"
                    name={`question-${index}`}
                    checked={answers[index] === i}
                    disabled={!test.remaining || !taking || busy}
                    onChange={() => choose(index, i)}
                  />
                  <span className="option-letter">{"ABCD"[i]}</span>
                  <Rich html={option} />
                </label>
              ))}
              {explanations[index] && (
                <div className="explanation">
                  <b>Explanation</b>
                  <Rich html={explanations[index]} />
                </div>
              )}
            </article>
          ))}
          {test.remaining && !taking && (
            <button
              className="primary"
              onClick={() => {
                setAnswers(Array(test.questions.length).fill(null));
                setTaking(true);
              }}
            >
              Start another attempt
            </button>
          )}
          {test.remaining && taking && (
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                act(async () => {
                  setBusy(true);
                  try {
                    const result = await request<{
                      explanations: string[];
                      counted_score: number;
                    }>(`workspace/attempts/${test.id}/submit`, { answers });
                    setExplanations(result.explanations);
                    setScore(result.counted_score);
                    const latest = await request<Attempt>(
                      `workspace/attempts/${test.id}`,
                    );
                    setTest(latest);
                    setTaking(false);
                    await refresh();
                  } finally {
                    setBusy(false);
                  }
                })
              }
            >
              {busy ? "Submitting…" : "Submit answers"}
            </button>
          )}
          <Table
            headers={["Attempt", "Score", "Submitted"]}
            rows={test.history.map((h, i) => [
              i + 1,
              h.score,
              new Date(h.submitted_at).toLocaleString(),
            ])}
          />
        </Panel>
      )}
      {user.role !== "student" && (
        <Panel title="Online MCQ results">
          <p>
            These scores remain separate from classroom marks and never
            determine attendance or the quarterly internal component.
          </p>
          <Table
            headers={[
              "Student",
              "Assessment",
              "Counted score",
              "Attempts",
              "Status",
              "Correction",
            ]}
            rows={data.assignments.map((a) => [
              data.students.find((s) => s.id === a.student_id)?.name,
              data.question_sets.find((q) => q.id === a.question_set_id)?.title,
              a.score ?? "—",
              a.history.length,
              <Badge value={a.submitted_at ? "submitted" : "pending"} />,
              user.role === "super_admin" && a.history.length > 0 ? (
                <button
                  className="secondary"
                  key="correct"
                  onClick={() => setCorrecting(a.id)}
                >
                  Correct attempt score
                </button>
              ) : null,
            ])}
          />
        </Panel>
      )}
      {correcting && (
        <Panel title="Authorised MCQ score correction">
          <p>
            Select the submitted attempt to correct. The original score and
            reason are retained in audit history. The counted result is
            recalculated using the test's first/latest/best policy.
          </p>
          <Form
            fields={[
              {
                key: "attempt_number",
                label: "Submitted attempt",
                options: (
                  data.assignments.find((a) => a.id === correcting)?.history ??
                  []
                ).map((h, i) => ({
                  id: i + 1,
                  name: `Attempt ${i + 1}: ${h.score}`,
                })),
              },
              {
                key: "score",
                label: "Corrected attempt score",
                type: "number",
              },
              {
                key: "reason",
                label: "Reason for correction",
                type: "textarea",
              },
            ]}
            submit={async (v) => {
              await request(`workspace/attempts/${correcting}/correct`, {
                attempt_number: +v.attempt_number,
                score: +v.score,
                reason: v.reason,
              });
              setCorrecting(null);
              await refresh();
            }}
            label="Save authorised correction"
          />
          <button className="link" onClick={() => setCorrecting(null)}>
            Cancel
          </button>
        </Panel>
      )}
    </>
  );
}

function QuestionEditor({
  item,
  onClose,
  onSave,
}: {
  item: QuestionSet;
  onClose: () => void;
  onSave: (
    questions: Question[],
    policy: Policy,
    title: string,
    category: string,
  ) => Promise<void>;
}) {
  const [questions, setQuestions] = useState(item.questions ?? []);
  const [title, setTitle] = useState(item.title);
  const locked = item.status !== "draft";
  const update = (index: number, change: Partial<Question>) =>
    setQuestions((current) =>
      current.map((q, i) => (i === index ? { ...q, ...change } : q)),
    );
  return (
    <Panel title="Review imported questions">
      <div className="actions">
        <button className="link" onClick={onClose}>
          Close editor
        </button>
        <Badge value={item.status} />
      </div>
      <label>
        Assessment title
        <input
          value={title}
          disabled={locked}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <p>
        Click any rich question, option, hint, or explanation to edit it.
        Changes are captured when the field loses focus. Review equations and
        diagrams before dispatch.
      </p>
      {questions.map((q, index) => (
        <article key={index} className="question">
          <h3>Question {index + 1}</h3>
          {locked ? (
            <Rich html={q.prompt} />
          ) : (
            <RichEditor
              value={q.prompt}
              onChange={(prompt) => update(index, { prompt })}
            />
          )}
          {q.options.map((option, i) => (
            <div key={i} className="option-editor">
              <label>
                <input
                  type="radio"
                  disabled={locked}
                  checked={q.correct === i}
                  onChange={() => update(index, { correct: i })}
                  name={`correct-${index}`}
                />
                {"ABCD"[i]} — correct answer
              </label>
              {locked ? (
                <Rich html={option} />
              ) : (
                <RichEditor
                  value={option}
                  onChange={(value) =>
                    update(index, {
                      options: q.options.map((o, j) => (j === i ? value : o)),
                    })
                  }
                />
              )}
            </div>
          ))}
          <h4>Hint (shown with question)</h4>
          {locked ? (
            <Rich html={q.hint} />
          ) : (
            <RichEditor
              value={q.hint}
              onChange={(hint) => update(index, { hint })}
            />
          )}
          <h4>Explanation (shown after submission)</h4>
          {locked ? (
            <Rich html={q.explanation ?? ""} />
          ) : (
            <RichEditor
              value={q.explanation ?? ""}
              onChange={(explanation) => update(index, { explanation })}
            />
          )}
        </article>
      ))}
      {!questions.length && <Empty />}
      {!locked && (
        <Form
          initial={Object.fromEntries(
            Object.entries(item.policy ?? {}).map(([k, v]) => [k, String(v)]),
          )}
          fields={[
            {
              key: "category",
              label: "Test purpose",
              value: item.category ?? "assessment",
              options: [
                { id: "assessment", name: "Classroom follow-up MCQ" },
                {
                  id: "practice",
                  name: "Online practice (eligible for leaderboard)",
                },
              ],
            },
            {
              key: "correct_marks",
              label: "Marks per correct answer",
              type: "number",
              min: 0.01,
            },
            {
              key: "incorrect_penalty",
              label: "Penalty per incorrect answer (0 for none)",
              type: "number",
              min: 0,
            },
            {
              key: "max_attempts",
              label: "Maximum attempts",
              type: "number",
              min: 1,
              max: 20,
            },
            {
              key: "counted_attempt",
              label: "Counted attempt",
              options: ["first", "latest", "best"].map((v) => ({
                id: v,
                name: v,
              })),
            },
          ]}
          submit={async (v) => {
            await onSave(
              questions,
              {
                correct_marks: +v.correct_marks,
                incorrect_penalty: +v.incorrect_penalty,
                max_attempts: +v.max_attempts,
                counted_attempt: v.counted_attempt,
              },
              title,
              v.category,
            );
          }}
          label="Save reviewed questions and scoring"
          resetOnSave={false}
        />
      )}
    </Panel>
  );
}
