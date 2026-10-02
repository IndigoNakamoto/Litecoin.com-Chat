"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { jobsApi, type JobStatus } from "@/lib/api";
import { CheckCircle2, Clock, Play, RefreshCw, XCircle } from "lucide-react";

function StatusIcon({ status }: { status: string | null }) {
  if (status === "success") return <CheckCircle2 className="h-4 w-4 text-green-600" />;
  if (status === "error") return <XCircle className="h-4 w-4 text-red-600" />;
  if (status === "running") return <RefreshCw className="h-4 w-4 animate-spin text-blue-600" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

function summarize(summary: Record<string, unknown> | null): string {
  if (!summary) return "–";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(summary)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) {
      if (v.length === 0) continue;
      parts.push(`${k}: ${v.length}`);
    } else if (typeof v === "object") {
      continue;
    } else {
      parts.push(`${k}: ${String(v)}`);
    }
  }
  return parts.slice(0, 8).join(" · ") || "–";
}

/**
 * Scheduled maintenance (ARQ cron) with last-run status, plus one-click runs.
 */
export function JobsPanel() {
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await jobsApi.status();
      setJobs(data.jobs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load job status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);

  const run = async (name: string, fn: () => Promise<{ job: string; job_id: string }>) => {
    setBusy(name);
    setMessage(null);
    setError(null);
    try {
      const res = await fn();
      setMessage(`Queued ${res.job} (job ${res.job_id}). Status refreshes automatically.`);
      setTimeout(load, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to enqueue ${name}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      {error && <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {message && <div className="rounded-md border border-green-300 bg-green-50 p-3 text-sm text-green-800">{message}</div>}

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-card-foreground">Scheduled maintenance</CardTitle>
              <CardDescription>
                Nightly: stale-doc report, golden-set eval, gap clustering. Weekly: embedding reconcile, reference-doc
                refresh. Alerts go to Discord only on failures, regressions, or new stale docs.
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading && jobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="divide-y divide-border">
              {jobs.map((j) => (
                <div key={j.name} className="flex flex-wrap items-start gap-3 py-3">
                  <div className="mt-0.5">
                    <StatusIcon status={j.last_status} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-card-foreground">{j.name}</span>
                      <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">{j.schedule}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">{j.description}</div>
                    <div className="mt-1 text-xs text-card-foreground">
                      Last run: {j.last_run ? new Date(j.last_run).toLocaleString() : "never"}
                      {j.last_status ? ` · ${j.last_status}` : ""}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground" title={summarize(j.summary)}>
                      {summarize(j.summary)}
                    </div>
                    {j.error && <div className="mt-1 text-xs text-red-700">{j.error}</div>}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() => run(j.name, () => jobsApi.runMaintenance(j.name))}
                  >
                    <Play className="mr-1.5 h-3.5 w-3.5" />
                    {busy === j.name ? "Queuing…" : "Run now"}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-card-foreground">On-demand</CardTitle>
          <CardDescription>Heavier operations. Reindex after CMS schema or embedding-model changes.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={busy !== null} onClick={() => run("reindex", () => jobsApi.reindex(false))}>
            Reindex vectors
          </Button>
          <Button variant="outline" disabled={busy !== null} onClick={() => run("reindex-faq", () => jobsApi.reindex(true))}>
            Reindex with FAQ
          </Button>
          <Button variant="outline" disabled={busy !== null} onClick={() => run("cleanup-orphans", () => jobsApi.cleanupOrphans())}>
            Cleanup orphan embeddings
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
