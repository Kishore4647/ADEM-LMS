import { useState } from "react";
import { API, request, roleName } from "./api";
import type { Data, User } from "./api";
import {
  Badge,
  Empty,
  Form,
  Mapping,
  nodePath,
  Panel,
  Table,
} from "./components";
export type PageProps = {
  data: Data;
  user: User;
  refresh: () => Promise<void>;
  act: (action: () => Promise<unknown>) => Promise<void>;
};

export function Schools({ data, refresh, act }: PageProps) {
  const [editing, setEditing] = useState<number | null>(null);
  const current = data.schools.find((s) => s.id === editing);
  return (
    <div className="two-column">
      <Panel title="Add school">
        <Form
          fields={[
            { key: "name", label: "School name" },
            { key: "code", label: "School code" },
            { key: "address", label: "Address", required: false },
          ]}
          submit={async (v) => {
            await request("admin/schools", v);
            await refresh();
          }}
          label="Create school"
        />
        {current && (
          <>
            <h3>Edit {current.name}</h3>
            <Form
              key={current.id}
              initial={{
                name: current.name,
                code: current.code,
                address: current.address ?? "",
              }}
              fields={[
                { key: "name", label: "School name" },
                { key: "code", label: "School code" },
                { key: "address", label: "Address", required: false },
              ]}
              submit={async (v) => {
                await request(`workspace/schools/${current.id}`, v, "PUT");
                setEditing(null);
                await refresh();
              }}
              label="Save school changes"
            />
            <button className="link" onClick={() => setEditing(null)}>
              Cancel edit
            </button>
          </>
        )}
      </Panel>
      <Panel title="Partner schools">
        <Table
          headers={["School", "Code", "Status"]}
          rows={data.schools.map((s) => [
            s.name,
            s.code,
            <>
              <Badge value={s.is_active ? "active" : "inactive"} />
              <button
                className="link"
                onClick={() =>
                  act(async () => {
                    await request(
                      `workspace/schools/${s.id}`,
                      { is_active: !s.is_active },
                      "PATCH",
                    );
                    await refresh();
                  })
                }
              >
                {s.is_active ? "Disable" : "Enable"}
              </button>
              <button className="link" onClick={() => setEditing(s.id)}>
                Edit details
              </button>
            </>,
          ])}
        />
      </Panel>
    </div>
  );
}

export function Users({ data, refresh, act, user }: PageProps) {
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [editSchools, setEditSchools] = useState<number[]>([]);
  const account = data.users.find((u) => u.id === editing);
  return (
    <>
      <div className="two-column">
        <Panel title="Provision Google account">
          <p>
            The account must sign in with this exact Google email. Choose its
            school access.
          </p>
          <Form
            fields={[
              { key: "full_name", label: "Full name" },
              { key: "email", label: "Google email", type: "email" },
              {
                key: "role",
                label: "Role",
                options: [
                  "content_uploader",
                  "ist",
                  "school_management",
                  "student",
                ].map((r) => ({ id: r, name: roleName(r) })),
              },
            ]}
            submit={async (v) => {
              await request("admin/users", { ...v, school_ids: selected });
              await refresh();
            }}
            label="Provision user"
          />
          <fieldset>
            <legend>School access</legend>
            {data.schools.map((s) => (
              <label className="check" key={s.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(s.id)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, s.id]
                        : selected.filter((id) => id !== s.id),
                    )
                  }
                />
                {s.name}
              </label>
            ))}
          </fieldset>
        </Panel>
        <Panel title="Authorised accounts">
          <Table
            headers={["Account", "Role", "Access", ""]}
            rows={data.users.map((u) => [
              <>
                <b>{u.full_name}</b>
                <small>{u.email}</small>
              </>,
              roleName(u.role),
              <Badge value={u.is_active ? "active" : "inactive"} />,
              <button
                className="secondary"
                onClick={() => {
                  setEditing(u.id);
                  setEditSchools(u.school_ids);
                }}
              >
                Manage
              </button>,
            ])}
          />
        </Panel>
      </div>
      {account && (
        <Panel title={`Manage ${account.email}`}>
          <fieldset>
            <legend>School access</legend>
            {data.schools.map((s) => (
              <label className="check" key={s.id}>
                <input
                  type="checkbox"
                  checked={editSchools.includes(s.id)}
                  onChange={(e) =>
                    setEditSchools(
                      e.target.checked
                        ? [...editSchools, s.id]
                        : editSchools.filter((id) => id !== s.id),
                    )
                  }
                />
                {s.name}
              </label>
            ))}
          </fieldset>
          <div className="actions">
            <button
              className="primary"
              onClick={() =>
                act(async () => {
                  await request(
                    `workspace/users/${account.id}`,
                    { school_ids: editSchools, is_active: account.is_active },
                    "PATCH",
                  );
                  await refresh();
                  setEditing(null);
                })
              }
            >
              Save access
            </button>
            <button
              className="secondary"
              disabled={account.id === user.id}
              onClick={() =>
                act(async () => {
                  await request(
                    `workspace/users/${account.id}`,
                    { school_ids: editSchools, is_active: !account.is_active },
                    "PATCH",
                  );
                  await refresh();
                  setEditing(null);
                })
              }
            >
              {account.is_active ? "Disable account" : "Enable account"}
            </button>
            <button className="link" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </Panel>
      )}
    </>
  );
}

export function Curriculum({ data, refresh }: PageProps) {
  const [editing, setEditing] = useState<number | null>(null);
  const current = data.nodes.find((n) => n.id === editing);
  const [board, setBoard] = useState("");
  const [level, setLevel] = useState("class");
  const parents: Record<string, string> = {
    subject: "class",
    chapter: "subject",
    topic: "chapter",
    sub_topic: "topic",
  };
  return (
    <>
      <div className="two-column">
        <Panel title="Create curriculum board">
          <Form
            fields={[{ key: "name", label: "Board name" }]}
            submit={async (v) => {
              await request("curriculum/boards", v);
              await refresh();
            }}
          />
        </Panel>
        <Panel title="Add curriculum record">
          <label>
            Board
            <select value={board} onChange={(e) => setBoard(e.target.value)}>
              <option value="">Select board</option>
              {data.boards.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Level
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              {["class", "subject", "chapter", "topic", "sub_topic"].map(
                (l) => (
                  <option key={l} value={l}>
                    {roleName(l)}
                  </option>
                ),
              )}
            </select>
          </label>
          {board && (
            <Form
              key={board + level}
              fields={[
                ...(level !== "class"
                  ? [
                      {
                        key: "parent_id",
                        label: "Parent",
                        options: data.nodes
                          .filter(
                            (n) =>
                              n.board_id === Number(board) &&
                              n.level === parents[level],
                          )
                          .map((n) => ({
                            id: n.id,
                            name: nodePath(data.nodes, n.id),
                          })),
                      },
                    ]
                  : []),
                { key: "name", label: roleName(level) + " name" },
                {
                  key: "sequence",
                  label: "Sequence",
                  type: "number",
                  value: "1",
                  min: 1,
                },
              ]}
              submit={async (v) => {
                await request("curriculum/nodes", {
                  board_id: Number(board),
                  level,
                  parent_id: v.parent_id ? Number(v.parent_id) : null,
                  name: v.name,
                  sequence: Number(v.sequence),
                });
                await refresh();
              }}
            />
          )}
        </Panel>
      </div>
      <Panel title="Curriculum sequence">
        {board && (
          <details>
            <summary>Rename selected curriculum board</summary>
            <Form
              key={`board-${board}`}
              initial={{
                name: data.boards.find((b) => b.id === +board)?.name ?? "",
              }}
              fields={[{ key: "name", label: "Board name" }]}
              submit={async (v) => {
                await request(`curriculum/boards/${board}`, v, "PATCH");
                await refresh();
              }}
              label="Save board name"
            />
          </details>
        )}
        <Table
          headers={["ID", "Board", "Level", "Path", "Order", "Edit"]}
          rows={data.nodes
            .filter((n) => !board || n.board_id === Number(board))
            .map((n) => [
              n.id,
              data.boards.find((b) => b.id === n.board_id)?.name,
              roleName(n.level),
              nodePath(data.nodes, n.id),
              n.sequence,
              <button
                key="edit"
                className="secondary"
                onClick={() => setEditing(n.id)}
              >
                Edit
              </button>,
            ])}
        />
      </Panel>
      {current && (
        <Panel title={`Edit ${current.name}`}>
          <p>
            The record identity and parent remain fixed so existing sessions and
            results retain their relationships.
          </p>
          <Form
            key={current.id}
            initial={{ name: current.name, sequence: String(current.sequence) }}
            fields={[
              { key: "name", label: "Name" },
              { key: "sequence", label: "Sequence", type: "number", min: 1 },
            ]}
            submit={async (v) => {
              await request(
                `curriculum/nodes/${current.id}`,
                { name: v.name, sequence: +v.sequence },
                "PATCH",
              );
              setEditing(null);
              await refresh();
            }}
          />
          <button className="link" onClick={() => setEditing(null)}>
            Cancel edit
          </button>
        </Panel>
      )}
    </>
  );
}

export function Enrolment({ data, user, refresh }: PageProps) {
  const canManage = ["super_admin", "school_management"].includes(user.role);
  const [editing, setEditing] = useState<number | null>(null);
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkSchool, setBulkSchool] = useState(0);
  const [bulkPreview, setBulkPreview] = useState<{
    total: number;
    valid: number;
    errors: { row: number; error: string }[];
  } | null>(null);
  const [bulkMessage, setBulkMessage] = useState("");

  async function sendBulk(commit: boolean) {
    if (!bulkFile || !bulkSchool) {
      setBulkMessage("Select a school and CSV file.");
      return;
    }
    const form = new FormData();
    form.set("school_id", String(bulkSchool));
    form.set("commit", String(commit));
    form.set("file", bulkFile);
    try {
      const result = await request<typeof bulkPreview>("workspace/students/bulk", form);
      setBulkPreview(result);
      setBulkMessage(commit ? `Imported ${result?.valid ?? 0} students.` : "Preview complete.");
      if (commit) await refresh();
    } catch (error) {
      setBulkMessage((error as Error).message);
    }
  }

  return (
    <>
      {canManage && (
        <div className="two-column">
          <Panel title="Add student">
          <Form
            fields={[
              { key: "full_name", label: "Student name" },
              { key: "email", label: "Google email", type: "email" },
              { key: "school_id", label: "School", options: data.schools },
              {
                key: "class_node_id",
                label: "Class",
                options: data.nodes
                  .filter((n) => n.level === "class")
                  .map((n) => ({
                    id: n.id,
                    name: `${data.boards.find((b) => b.id === n.board_id)?.name} / ${n.name}`,
                  })),
              },
              { key: "section", label: "Section (for example, A)" },
              { key: "academic_year", label: "Academic year", value: "2026-2027" },
              { key: "admission_number", label: "Admission number" },
            ]}
            submit={async (v) => {
              await request("workspace/students", {
                ...v,
                school_id: +v.school_id,
                class_node_id: +v.class_node_id,
              });
              await refresh();
            }}
            label="Enrol student"
          />
        </Panel>
          <Panel title="Bulk student import">
            <p className="muted">
              CSV columns: admission_number, full_name, email, board, class,
              section, academic_year. Preview must have no errors before import.
            </p>
            <label className="file-input">
              School
              <select value={bulkSchool} onChange={(e) => setBulkSchool(+e.target.value)}>
                <option value={0}>Select…</option>
                {data.schools.map((school) => (
                  <option key={school.id} value={school.id}>{school.name}</option>
                ))}
              </select>
            </label>
            <label className="file-input">
              Student CSV
              <input type="file" accept=".csv,text/csv" onChange={(e) => {
                setBulkFile(e.target.files?.[0] ?? null);
                setBulkPreview(null);
              }} />
            </label>
            <div className="button-row">
              <button className="secondary" onClick={() => void sendBulk(false)}>Preview</button>
              <button className="primary" disabled={!bulkPreview || bulkPreview.errors.length > 0} onClick={() => void sendBulk(true)}>Import valid preview</button>
            </div>
            {bulkMessage && <p className="muted">{bulkMessage}</p>}
            {bulkPreview && (
              <p className={bulkPreview.errors.length ? "error" : "success"}>
                {bulkPreview.valid} of {bulkPreview.total} valid.
                {bulkPreview.errors.slice(0, 5).map((e) => ` Row ${e.row}: ${e.error}`).join(" ")}
              </p>
            )}
          </Panel>
        </div>
      )}
      {user.role === "super_admin" && (
        <Panel title="Assign IST subject">
          <Form
            fields={[
              {
                key: "user_id",
                label: "Trainer",
                options: data.users
                  .filter((u) => u.role === "ist")
                  .map((u) => ({ id: u.id, name: u.full_name || u.email })),
              },
              { key: "school_id", label: "School", options: data.schools },
              {
                key: "subject_id",
                label: "Class / subject",
                options: data.nodes
                  .filter((n) => n.level === "subject")
                  .map((n) => ({ id: n.id, name: nodePath(data.nodes, n.id) })),
              },
            ]}
            submit={async (v) => {
              await request("workspace/teaching", {
                user_id: +v.user_id,
                school_id: +v.school_id,
                subject_id: +v.subject_id,
              });
              await refresh();
            }}
            label="Assign trainer"
          />
        </Panel>
      )}
      {canManage && (
        <Panel title="Close academic year">
          <p className="muted">
            This promotes active students, keeps retained students in the same
            class, and graduates students in the final class. This cannot be
            repeated for the same year.
          </p>
          <Form
            fields={[
              { key: "school_id", label: "School", options: data.schools },
              { key: "current_academic_year", label: "Closing year", value: "2026-2027" },
              { key: "next_academic_year", label: "Next year", value: "2027-2028" },
            ]}
            submit={async (v) => {
              if (!window.confirm(
                `Close ${v.current_academic_year} and update every active student in this school?`,
              )) throw new Error("Academic-year closure cancelled.");
              await request(`workspace/schools/${+v.school_id}/close-academic-year`, {
                current_academic_year: v.current_academic_year,
                next_academic_year: v.next_academic_year,
              });
              await refresh();
            }}
            label="Close year and promote students"
          />
        </Panel>
      )}
      <Panel title="Student enrolments">
        <Table
          headers={["Student", "School", "Class / section", "Academic year", "Admission", "Status", "Actions"]}
          rows={data.students.map((s) => [
            <div key={s.id}><strong>{s.name}</strong><br /><span className="muted">{s.email}</span></div>,
            data.schools.find((x) => x.id === s.school_id)?.name,
            `${nodePath(data.nodes, s.class_node_id)} / ${s.section || "—"}`,
            s.academic_year || "Not assigned",
            s.admission_number,
            <Badge key={`status-${s.id}`} value={s.status} />,
            <div className="button-row" key={`actions-${s.id}`}>
              {s.status === "active" && (
                <button className="secondary" onClick={async () => {
                  await request(`workspace/students/${s.id}/retention`, { retain: !s.retain_next_year }, "PATCH");
                  await refresh();
                }}>{s.retain_next_year ? "Cancel retention" : "Retain next year"}</button>
              )}
              {canManage && <button className="secondary" onClick={() => setEditing(s.id)}>Edit</button>}
            </div>,
          ])}
        />
      </Panel>
      {editing && (() => {
        const student = data.students.find((s) => s.id === editing)!;
        return (
          <Panel title={`Edit ${student.name}`}>
            <Form
              initial={{ full_name: student.name, email: student.email, admission_number: student.admission_number, section: student.section, academic_year: student.academic_year || "2026-2027" }}
              resetOnSave={false}
              fields={[
                { key: "full_name", label: "Student name" },
                { key: "email", label: "Google email", type: "email" },
                { key: "admission_number", label: "Admission number" },
                { key: "section", label: "Section" },
                { key: "academic_year", label: "Academic year" },
              ]}
              submit={async (v) => {
                await request(`workspace/students/${editing}`, v, "PUT");
                setEditing(null);
                await refresh();
              }}
              label="Update student"
            />
          </Panel>
        );
      })()}
      {user.role === "super_admin" && <Panel title="Teaching assignments">
        <Table
          headers={["Trainer", "School", "Subject"]}
          rows={data.teaching.map((a) => [
            data.users.find((u) => u.id === a.user_id)?.full_name,
            data.schools.find((s) => s.id === a.school_id)?.name,
            nodePath(data.nodes, a.subject_id),
          ])}
        />
      </Panel>}
    </>
  );
}

export function Resources({ data, user, refresh, act }: PageProps) {
  const [mapping, setMapping] = useState({ school_id: 0, subtopic_id: 0 });
  const [file, setFile] = useState<File | null>(null);
  const [view, setView] = useState<number | null>(null);
  const canUpload = ["super_admin", "content_uploader", "ist"].includes(
    user.role,
  );
  const [filter, setFilter] = useState("");
  return (
    <>
      {canUpload && (
        <Panel title="Add learning resource">
          <Mapping data={data} onChange={setMapping} />
          <Form
            fields={[
              { key: "title", label: "Resource title" },
              {
                key: "drive_url",
                label:
                  "Google Drive video link (leave blank to upload document)",
                type: "url",
                required: false,
              },
              {
                key: "published",
                label: "Visibility",
                options: [
                  { id: "false", name: "Draft" },
                  { id: "true", name: "Publish to assigned students" },
                ],
              },
            ]}
            submit={async (v) => {
              if (!mapping.school_id || !mapping.subtopic_id)
                throw Error("Select school and the complete curriculum path.");
              let file_id: number | undefined;
              if (file && !v.drive_url) {
                const form = new FormData();
                form.set("file", file);
                file_id = (
                  await request<{ id: number }>("workspace/files", form)
                ).id;
              }
              await request("workspace/assets", {
                ...mapping,
                title: v.title,
                drive_url: v.drive_url || null,
                file_id: file_id ?? null,
                published: v.published === "true",
              });
              setFile(null);
              await refresh();
            }}
            label="Save resource"
          />
          <label className="file-input">
            Document or supplementary material
            <input
              type="file"
              accept=".pdf,.docx,.png,.jpg,.jpeg,.mp3,.xlsx,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <p className="muted">
            Videos use Google Drive permissions. Viewers must sign into the
            authorised Google account. Other uploads are private application
            files.
          </p>
        </Panel>
      )}
      <Panel title="Learning library">
        <input
          aria-label="Search resources"
          placeholder="Search title or curriculum…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <div className="resource-grid">
          {data.assets
            .filter((a) =>
              (a.title + nodePath(data.nodes, a.subtopic_id))
                .toLowerCase()
                .includes(filter.toLowerCase()),
            )
            .map((a) => (
              <article className="resource-card" key={a.id}>
                <div className="resource-icon">
                  {a.kind === "video" ? "▶" : "▤"}
                </div>
                <Badge value={a.published ? "published" : "draft"} />
                <h3>{a.title}</h3>
                <p>{nodePath(data.nodes, a.subtopic_id)}</p>
                {a.issue && <p className="error">Reported issue: {a.issue}</p>}
                {a.ready_by && (
                  <p>
                    {a.ready_by.length} trainer(s) confirmed media readiness.
                  </p>
                )}
                <div className="actions">
                  {user.role === "ist" && (
                    <button
                      className="secondary"
                      onClick={() =>
                        act(async () => {
                          await request(`workspace/assets/${a.id}/ready`, {
                            ready: !a.ready_by?.includes(user.id),
                          });
                          await refresh();
                        })
                      }
                    >
                      {a.ready_by?.includes(user.id)
                        ? "Undo readiness"
                        : "Confirm readiness"}
                    </button>
                  )}
                  <button
                    className="primary"
                    onClick={() => setView(view === a.id ? null : a.id)}
                  >
                    {view === a.id ? "Close" : "Open"}
                  </button>
                  {["super_admin", "content_uploader"].includes(user.role) && (
                    <button
                      className="secondary"
                      onClick={() =>
                        act(async () => {
                          await request(`workspace/assets/${a.id}/publish`, {});
                          await refresh();
                        })
                      }
                    >
                      {a.published ? "Unpublish" : "Publish"}
                    </button>
                  )}
                  {canUpload && (
                    <button
                      className="link"
                      onClick={() => {
                        const issue = window.prompt(
                          "Describe the content problem",
                        );
                        if (issue)
                          void act(async () => {
                            await request(`workspace/assets/${a.id}/issue`, {
                              issue,
                            });
                            await refresh();
                          });
                      }}
                    >
                      Report issue
                    </button>
                  )}
                </div>
                {view === a.id &&
                  (a.drive_id ? (
                    <iframe
                      title={a.title}
                      src={`https://drive.google.com/file/d/${a.drive_id}/preview`}
                      allow="fullscreen"
                      allowFullScreen
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <a
                      className="download"
                      href={`${API}/api/workspace/files/${a.file_id}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open / download resource
                    </a>
                  ))}
              </article>
            ))}
        </div>
        {!data.assets.length && <Empty>No resources assigned yet.</Empty>}
      </Panel>
    </>
  );
}
