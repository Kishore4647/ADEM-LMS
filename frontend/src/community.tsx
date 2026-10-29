import { useCallback, useEffect, useState } from "react";
import "./community.css";
import { request } from "./api";
import { Empty, Form, Panel, Table } from "./components";
import type { PageProps } from "./setup";

type CommunityConfig = {
  ranking: string;
  week_starts: number;
  timezone: string;
  hall_student_ids: number[];
  public_display_authorised: boolean;
};
type Ranking = {
  configured: boolean;
  week_start: string;
  metric: string;
  rows: {
    rank: number;
    name: string;
    class_name: string;
    score: number;
    tests: number;
  }[];
};
export function Community({ data, user, act }: PageProps) {
  const [config, setConfig] = useState<CommunityConfig | null>(null);
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [hall, setHall] = useState<number[]>([]);
  const [authorised, setAuthorised] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setRanking(await request<Ranking>("workspace/leaderboard"));
    if (user.role === "super_admin") {
      const settings = await request<CommunityConfig | null>(
        "workspace/community/settings",
      );
      setConfig(settings);
      setHall(settings?.hall_student_ids ?? []);
      setAuthorised(settings?.public_display_authorised ?? false);
    }
  }, [user.role]);
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, [load]);
  return (
    <>
      {error && <p className="error">{error}</p>}
      <Panel title="Weekly online practice leaderboard">
        {ranking?.configured ? (
          <>
            <p>
              Week beginning {ranking.week_start} ·{" "}
              {ranking.metric.replaceAll("_", " ")}. Equal scores share the same
              rank.
            </p>
            <Table
              headers={["Rank", "Student", "Class", "Score", "Practice tests"]}
              rows={ranking.rows.map((r) => [
                r.rank,
                r.name,
                r.class_name,
                r.score,
                r.tests,
              ])}
            />
          </>
        ) : (
          <Empty>Leaderboard settings have not been configured.</Empty>
        )}
      </Panel>
      {user.role === "super_admin" && (
        <Panel title="Leaderboard and public Hall of Fame settings">
          <p>
            Only dispatched question sets marked as Online practice are eligible
            for the weekly leaderboard. Public Hall of Fame entries expose the
            approved student's name and class only.
          </p>
          <Form
            key={JSON.stringify(config)}
            initial={
              config
                ? {
                    ranking: config.ranking,
                    week_starts: String(config.week_starts),
                    timezone: config.timezone,
                  }
                : {}
            }
            fields={[
              {
                key: "ranking",
                label: "Ranking metric",
                options: [
                  { id: "average_percentage", name: "Average test percentage" },
                  { id: "total_marks", name: "Sum of counted test marks" },
                ],
              },
              {
                key: "week_starts",
                label: "Reporting week starts",
                options: [
                  { id: "0", name: "Monday" },
                  { id: "6", name: "Sunday" },
                ],
              },
              {
                key: "timezone",
                label: "Reporting timezone (IANA)",
                value: "Asia/Kolkata",
              },
            ]}
            submit={async (v) => {
              await request(
                "workspace/community/settings",
                {
                  ranking: v.ranking,
                  week_starts: +v.week_starts,
                  timezone: v.timezone,
                  hall_student_ids: hall,
                  public_display_authorised: authorised,
                },
                "PUT",
              );
              await load();
            }}
            label="Save community settings"
          />
          <fieldset>
            <legend>Students approved for public Hall of Fame</legend>
            <label className="check">
              <input
                type="checkbox"
                checked={authorised}
                onChange={(e) => setAuthorised(e.target.checked)}
              />
              I confirm the selected students are authorised for public display.
            </label>
            {data.students.map((s) => (
              <label key={s.id} className="check">
                <input
                  type="checkbox"
                  checked={hall.includes(s.id)}
                  onChange={(e) =>
                    setHall(
                      e.target.checked
                        ? [...hall, s.id]
                        : hall.filter((id) => id !== s.id),
                    )
                  }
                />
                {s.name}
              </label>
            ))}
          </fieldset>
          <button className="link" onClick={() => act(load)}>
            Refresh rankings
          </button>
        </Panel>
      )}
    </>
  );
}
