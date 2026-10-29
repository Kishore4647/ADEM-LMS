export const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function request<T = unknown>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const options: RequestInit = {
    credentials: "include",
    method: body === undefined ? "GET" : method,
  };
  if (body instanceof FormData) options.body = body;
  else if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(`${API}/api/${path}`, options);
  const result =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = result?.detail;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((x) => `${x.loc?.slice(1).join(".")}: ${x.msg}`).join("; ")
        : typeof detail === "string"
          ? detail
          : `Request failed (${response.status})`,
    );
  }
  return result as T;
}

export type User = {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  school_ids: number[];
};
export type School = {
  id: number;
  name: string;
  code: string;
  address: string;
  is_active: boolean;
};
export type Board = { id: number; name: string };
export type Node = {
  id: number;
  board_id: number;
  parent_id: number | null;
  name: string;
  level: string;
  sequence: number;
};
export type Student = {
  id: number;
  user_id: number;
  school_id: number;
  class_node_id: number;
  name: string;
  admission_number: string;
};
export type Teaching = {
  id: number;
  user_id: number;
  school_id: number;
  subject_id: number;
};
export type Asset = {
  ready_by?: number[];
  id: number;
  school_id: number;
  subtopic_id: number;
  title: string;
  kind: string;
  drive_id: string | null;
  file_id: number | null;
  published: boolean;
  issue: string | null;
};
export type Session = {
  id: number;
  school_id: number;
  subject_id: number;
  trainer_id: number;
  session_date: string;
  period: string;
  subtopic_ids: number[];
  notes: string;
  status: string;
  review_comment: string;
};
export type Mark = {
  id: number;
  student_id: number;
  subject_node_id: number;
  component: string;
  academic_period: string;
  title: string;
  obtained_marks: number | null;
  maximum_marks: number;
  is_absent: boolean;
};
export type Attendance = {
  mark_id: number;
  session_id: number;
  student_id: number;
  manual_present: boolean;
  final_status: string;
};
export type Policy = {
  correct_marks: number;
  incorrect_penalty: number;
  max_attempts: number;
  counted_attempt: string;
};
export type Question = {
  prompt: string;
  options: string[];
  hint: string;
  explanation?: string;
  correct?: number;
};
export type QuestionSet = {
  category: string;
  id: number;
  school_id: number;
  subtopic_id: number;
  title: string;
  difficulty: string;
  status: string;
  source_file_id?: number;
  question_count: number;
  questions?: Question[];
  policy: Policy;
};
export type Assignment = {
  id: number;
  question_set_id: number;
  student_id: number;
  score: number | null;
  submitted_at: string | null;
  history: { score: number; submitted_at: string }[];
};
export type Result = {
  assessment: number | null;
  activity: number | null;
  exam: number | null;
  total: number | null;
  complete: boolean;
};
export type Publication = {
  id: number;
  student_id: number;
  subject_id: number;
  period: string;
  stale: boolean;
  snapshot: Result;
};
export type Data = {
  schools: School[];
  users: User[];
  boards: Board[];
  nodes: Node[];
  students: Student[];
  teaching: Teaching[];
  assets: Asset[];
  sessions: Session[];
  marks: Mark[];
  attendance: Attendance[];
  question_sets: QuestionSet[];
  assignments: Assignment[];
  publications: Publication[];
};
export const roleName = (value: string) =>
  value === "ist"
    ? "IST"
    : value
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
