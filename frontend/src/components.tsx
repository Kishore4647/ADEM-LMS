import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import DOMPurify from "dompurify";
import type { Data, Node } from "./api";

export type Option = { id: string | number; name: string };
export type Field = {
  key: string;
  label: string;
  type?: string;
  options?: Option[];
  value?: string;
  required?: boolean;
  min?: number;
  max?: number;
};
export function Form({
  fields,
  submit,
  label = "Save",
  initial = {},
  resetOnSave = true,
}: {
  fields: Field[];
  submit: (values: Record<string, string>) => Promise<unknown>;
  label?: string;
  initial?: Record<string, string>;
  resetOnSave?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    const element = event.currentTarget;
    const data = Object.fromEntries(new FormData(element).entries()) as Record<
      string,
      string
    >;
    try {
      await submit(data);
      if (resetOnSave) element.reset();
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={send} className="data-form">
      {fields.map((field) => (
        <label key={field.key}>
          {field.label}
          {field.options ? (
            <select
              name={field.key}
              defaultValue={initial[field.key] ?? field.value ?? ""}
              required={field.required !== false}
            >
              <option value="">Select…</option>
              {field.options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          ) : field.type === "textarea" ? (
            <textarea
              name={field.key}
              defaultValue={initial[field.key]}
              required={field.required !== false}
              rows={3}
            />
          ) : (
            <input
              name={field.key}
              type={field.type ?? "text"}
              defaultValue={initial[field.key] ?? field.value}
              required={field.required !== false}
              min={field.min}
              max={field.max}
              step={field.type === "number" ? "any" : undefined}
            />
          )}
        </label>
      ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="success" role="status">
          Saved successfully.
        </p>
      )}
      <button className="primary" disabled={busy}>
        {busy ? "Saving…" : label}
      </button>
    </form>
  );
}
export function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export function Empty({
  children = "No records yet.",
}: {
  children?: ReactNode;
}) {
  return <div className="empty">{children}</div>;
}
export function Badge({ value }: { value: string }) {
  return <span className={`badge ${value}`}>{value.replaceAll("_", " ")}</span>;
}
export function Rich({ html }: { html: string }) {
  return (
    <div
      className="rich"
      dangerouslySetInnerHTML={{
        __html: DOMPurify.sanitize(html, {
          USE_PROFILES: { html: true, mathMl: true },
        }),
      }}
    />
  );
}
export function RichEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div
      className="rich editor"
      contentEditable
      suppressContentEditableWarning
      onBlur={(event) =>
        onChange(
          DOMPurify.sanitize(event.currentTarget.innerHTML, {
            USE_PROFILES: { html: true, mathMl: true },
          }),
        )
      }
      dangerouslySetInnerHTML={{
        __html: DOMPurify.sanitize(value, {
          USE_PROFILES: { html: true, mathMl: true },
        }),
      }}
    />
  );
}
export function Table({
  headers,
  rows,
}: {
  headers: string[];
  rows: ReactNode[][];
}) {
  return rows.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, i) => (
                <td key={i}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty />
  );
}
export function nodePath(nodes: Node[], id: number): string {
  const chain: string[] = [];
  let node = nodes.find((n) => n.id === id);
  while (node) {
    chain.unshift(node.name);
    node = nodes.find((n) => n.id === node?.parent_id);
  }
  return chain.join(" / ");
}
export function Mapping({
  data,
  onChange,
}: {
  data: Data;
  onChange: (mapping: { school_id: number; subtopic_id: number }) => void;
}) {
  const [school, setSchool] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const levels = ["class", "subject", "chapter", "topic", "sub_topic"];
  function updateSchool(value: string) {
    setSchool(value);
    onChange({ school_id: Number(value), subtopic_id: selected[4] ?? 0 });
  }
  function update(index: number, value: number) {
    const next = [...selected.slice(0, index), value];
    setSelected(next);
    onChange({ school_id: Number(school), subtopic_id: next[4] ?? 0 });
  }
  return (
    <div className="mapping">
      <label>
        School
        <select value={school} onChange={(e) => updateSchool(e.target.value)}>
          <option value="">Select school</option>
          {data.schools.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      {levels.map((level, i) => (
        <label key={level}>
          {level.replace("_", " ")}
          <select
            value={selected[i] ?? ""}
            onChange={(e) => update(i, Number(e.target.value))}
            disabled={i > 0 && !selected[i - 1]}
          >
            <option value="">Select {level.replace("_", " ")}</option>
            {data.nodes
              .filter(
                (n) =>
                  n.level === level && (!i || n.parent_id === selected[i - 1]),
              )
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {!i
                    ? `${data.boards.find((b) => b.id === n.board_id)?.name} · `
                    : ""}
                  {n.name}
                </option>
              ))}
          </select>
        </label>
      ))}
    </div>
  );
}
