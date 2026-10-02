"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { feedbackApi, type FeedbackBySource, type FeedbackItem } from "@/lib/api";
import { ThumbsDown, ThumbsUp, RefreshCw } from "lucide-react";

const CMS_URL = process.env.NEXT_PUBLIC_PAYLOAD_URL || "";

function cmsEditLink(payloadId: string): string | null {
  if (!CMS_URL) return null;
  return `${CMS_URL.replace(/\/$/, "")}/admin/collections/articles/${payloadId}`;
}

/**
 * Thumbs feedback, grouped by the cited source document.
 *
 * A thumbs-down is filed against the article(s) the answer cited, not the model,
 * so this view is a prioritised list of documents to fix or re-date.
 */
export function FeedbackReview() {
  const [bySource, setBySource] = useState<FeedbackBySource[]>([]);
  const [recent, setRecent] = useState<FeedbackItem[]>([]);
  const [totals, setTotals] = useState<{ up: number | null; down: number | null }>({ up: null, down: null });
  const [days, setDays] = useState(30);
  const [verdict, setVerdict] = useState<"all" | "down" | "up">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [src, list] = await Promise.all([
        feedbackApi.bySource(days),
        feedbackApi.list({ days, limit: 100, verdict: verdict === "all" ? undefined : verdict }),
      ]);
      setBySource(src.items);
      setRecent(list.items);
      if (verdict === "all") setTotals(list.totals);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load feedback");
    } finally {
      setLoading(false);
    }
  }, [days, verdict]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Window:</span>
        {[7, 30, 90].map((d) => (
          <Button key={d} size="sm" variant={days === d ? "default" : "outline"} onClick={() => setDays(d)}>
            {d}d
          </Button>
        ))}
        <span className="ml-4 text-sm text-muted-foreground">Verdict:</span>
        {(["all", "down", "up"] as const).map((v) => (
          <Button key={v} size="sm" variant={verdict === v ? "default" : "outline"} onClick={() => setVerdict(v)}>
            {v}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={load} disabled={loading} className="ml-auto">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {error && <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-card-foreground">Thumbs up</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-2xl font-bold text-green-700">
              <ThumbsUp className="h-5 w-5" /> {totals.up ?? "–"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-card-foreground">Thumbs down</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-2xl font-bold text-red-700">
              <ThumbsDown className="h-5 w-5" /> {totals.down ?? "–"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-card-foreground">Documents flagged</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-card-foreground">{bySource.filter((s) => s.down > 0).length}</div>
            <p className="mt-1 text-xs text-muted-foreground">cited by at least one thumbs-down answer</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-card-foreground">By source document</CardTitle>
          <CardDescription>
            Worst first. Most “wrong answers” are stale or missing chunks: open the article, fix or re-date it,
            and the chip label and cached answers refresh on publish.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {bySource.length === 0 ? (
            <p className="text-sm text-muted-foreground">No feedback with cited sources in this window.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Article</th>
                    <th className="py-2 pr-4">👎</th>
                    <th className="py-2 pr-4">👍</th>
                    <th className="py-2 pr-4">Reasons</th>
                    <th className="py-2 pr-4">Sample questions</th>
                    <th className="py-2">Last</th>
                  </tr>
                </thead>
                <tbody>
                  {bySource.map((row) => {
                    const link = cmsEditLink(row.payload_id);
                    return (
                      <tr key={row.payload_id} className="border-t border-border align-top">
                        <td className="py-2 pr-4 font-mono text-xs">
                          {link ? (
                            <a href={link} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                              {row.payload_id}
                            </a>
                          ) : (
                            row.payload_id
                          )}
                        </td>
                        <td className="py-2 pr-4 font-semibold text-red-700">{row.down}</td>
                        <td className="py-2 pr-4 text-green-700">{row.up}</td>
                        <td className="py-2 pr-4 text-xs">
                          {Object.entries(row.reasons).length === 0
                            ? "–"
                            : Object.entries(row.reasons)
                                .sort((a, b) => b[1] - a[1])
                                .map(([k, v]) => `${k} ×${v}`)
                                .join(", ")}
                        </td>
                        <td className="py-2 pr-4 text-xs text-muted-foreground">
                          {row.sample_questions.slice(0, 3).map((q, i) => (
                            <div key={i} className="truncate" title={q}>
                              {q}
                            </div>
                          ))}
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {row.last_feedback ? new Date(row.last_feedback).toLocaleDateString() : "–"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-card-foreground">Recent feedback</CardTitle>
          <CardDescription>Newest first, {recent.length} shown.</CardDescription>
        </CardHeader>
        <CardContent>
          {recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {recent.map((f) => (
                <li key={f.id} className="flex gap-3 py-2 text-sm">
                  {f.verdict === "up" ? (
                    <ThumbsUp className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
                  ) : (
                    <ThumbsDown className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-card-foreground">{f.user_question || <span className="text-muted-foreground">(question not logged)</span>}</div>
                    <div className="text-xs text-muted-foreground">
                      {new Date(f.timestamp).toLocaleString()}
                      {f.reason ? ` · ${f.reason}` : ""}
                      {f.source_payload_ids.length ? ` · ${f.source_payload_ids.length} source(s)` : " · no sources"}
                      {f.comment ? ` · “${f.comment}”` : ""}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
