"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { knowledgeCandidatesApi, KnowledgeCandidate } from "@/lib/api";

type StatusFilter = "all" | "pending" | "approved" | "rejected" | "published";

interface Stats {
  by_status: Record<string, { count: number; total_frequency: number }>;
  top_pending_topics: Array<{
    topic: string;
    count: number;
    total_frequency: number;
  }>;
  total_candidates: number;
}

export function KnowledgeCandidates() {
  const [candidates, setCandidates] = useState<KnowledgeCandidate[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [noteInputs, setNoteInputs] = useState<Record<string, string>>({});

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [listData, statsData] = await Promise.all([
        knowledgeCandidatesApi.list({
          status: statusFilter === "all" ? undefined : statusFilter,
          limit,
          offset,
          sort_by: "question_frequency",
          sort_order: -1,
        }),
        knowledgeCandidatesApi.stats(),
      ]);
      setCandidates(listData.candidates);
      setTotal(listData.total);
      setStats(statsData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch candidates"
      );
    } finally {
      setLoading(false);
    }
  }, [statusFilter, limit, offset]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleApprove = async (id: string) => {
    setActionLoading(id);
    try {
      await knowledgeCandidatesApi.update(id, {
        status: "approved",
        admin_notes: noteInputs[id] || undefined,
      });
      await fetchData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to approve candidate"
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: string) => {
    setActionLoading(id);
    try {
      await knowledgeCandidatesApi.update(id, {
        status: "rejected",
        admin_notes: noteInputs[id] || undefined,
      });
      await fetchData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to reject candidate"
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handlePublish = async (id: string) => {
    setActionLoading(id);
    try {
      const result = await knowledgeCandidatesApi.publish(id);
      if (result.published) {
        await fetchData();
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to publish candidate"
      );
    } finally {
      setActionLoading(null);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: "bg-yellow-700 text-white",
      approved: "bg-green-700 text-white",
      rejected: "bg-red-700 text-white",
      published: "bg-blue-700 text-white",
    };
    return (
      <span
        className={`text-xs px-2 py-0.5 rounded font-semibold ${styles[status] || "bg-gray-600 text-white"}`}
      >
        {status}
      </span>
    );
  };

  const statusFilterOptions: StatusFilter[] = [
    "all",
    "pending",
    "approved",
    "rejected",
    "published",
  ];

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {(["pending", "approved", "rejected", "published"] as const).map(
            (s) => {
              const data = stats.by_status[s];
              return (
                <Card key={s}>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-card-foreground">
                      {data?.count || 0}
                    </div>
                    <div className="text-xs text-muted-foreground capitalize">
                      {s}
                    </div>
                    {data?.total_frequency && data.total_frequency > data.count && (
                      <div className="text-xs text-muted-foreground mt-1">
                        {data.total_frequency} total asks
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            }
          )}
          <Card>
            <CardContent className="p-4 text-center">
              <div className="text-2xl font-bold text-card-foreground">
                {stats.total_candidates}
              </div>
              <div className="text-xs text-muted-foreground">Total</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Top Pending Topics */}
      {stats && stats.top_pending_topics.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Top Pending Topics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {stats.top_pending_topics.map((topic) => (
                <span
                  key={topic.topic}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-muted text-foreground border border-border"
                >
                  {topic.topic}
                  <span className="text-muted-foreground">
                    ({topic.count} / {topic.total_frequency} asks)
                  </span>
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Candidates List */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center flex-wrap gap-4">
            <div>
              <CardTitle>Knowledge Gap Candidates</CardTitle>
              <CardDescription>
                Questions where search grounding supplemented the knowledge base
              </CardDescription>
            </div>
            <div className="flex gap-2 items-center">
              <span className="text-sm font-medium text-foreground">
                Status:
              </span>
              <div className="flex gap-1 border rounded-md p-1 bg-muted/50">
                {statusFilterOptions.map((s) => (
                  <Button
                    key={s}
                    variant={statusFilter === s ? "default" : "ghost"}
                    size="sm"
                    onClick={() => {
                      setStatusFilter(s);
                      setOffset(0);
                    }}
                    className="h-7 px-3 text-xs capitalize"
                  >
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading && candidates.length === 0 ? (
            <div className="text-center py-8 text-foreground">
              Loading candidates...
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-red-600 dark:text-red-400">Error: {error}</p>
              <Button variant="outline" className="mt-2" onClick={fetchData}>
                Retry
              </Button>
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No {statusFilter !== "all" ? statusFilter : ""} candidates found
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">
                Showing {candidates.length} of {total} candidates
              </div>
              {candidates.map((candidate) => (
                <div
                  key={candidate.id}
                  className="border rounded-lg bg-card hover:bg-muted/50 transition-colors"
                >
                  {/* Header row */}
                  <div
                    className="p-4 cursor-pointer"
                    onClick={() =>
                      setExpandedId(
                        expandedId === candidate.id ? null : candidate.id
                      )
                    }
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="text-sm font-medium text-foreground">
                            {formatTimestamp(candidate.timestamp)}
                          </span>
                          {getStatusBadge(candidate.status)}
                          {candidate.question_frequency > 1 && (
                            <span className="text-xs px-2 py-0.5 rounded font-semibold bg-purple-700 text-white">
                              {candidate.question_frequency}x asked
                            </span>
                          )}
                          {candidate.topic_cluster && (
                            <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground border border-border">
                              {candidate.topic_cluster}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-foreground font-medium">
                          {candidate.user_question}
                        </p>
                      </div>
                      <div className="text-xs text-muted-foreground ml-4 shrink-0">
                        KB coverage:{" "}
                        {(candidate.kb_coverage_score * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>

                  {/* Expanded detail */}
                  {expandedId === candidate.id && (
                    <div className="px-4 pb-4 border-t border-border pt-4 space-y-4">
                      {/* Generated answer */}
                      <div>
                        <h4 className="text-sm font-semibold text-foreground mb-2">
                          Generated Answer
                        </h4>
                        <div className="bg-muted/50 rounded p-3 text-sm text-foreground whitespace-pre-wrap max-h-96 overflow-y-auto">
                          {candidate.generated_answer}
                        </div>
                      </div>

                      {/* Grounding sources */}
                      {candidate.grounding_sources.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold text-foreground mb-2">
                            Web Sources Used
                          </h4>
                          <ul className="space-y-1">
                            {candidate.grounding_sources.map((src, i) => (
                              <li key={i} className="text-sm">
                                {src.url ? (
                                  <a
                                    href={src.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-500 hover:text-blue-600 underline"
                                  >
                                    {src.title || src.url}
                                  </a>
                                ) : (
                                  <span className="text-muted-foreground">
                                    {src.title || "Unknown source"}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Metadata */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-muted-foreground">
                        <div>
                          <span className="font-medium">Request ID:</span>{" "}
                          <span className="font-mono">
                            {candidate.request_id.slice(0, 8)}...
                          </span>
                        </div>
                        <div>
                          <span className="font-medium">KB Sources:</span>{" "}
                          {candidate.kb_sources_used.length}
                        </div>
                        <div>
                          <span className="font-medium">Similar IDs:</span>{" "}
                          {candidate.similar_candidate_ids.length}
                        </div>
                        {candidate.payload_article_id && (
                          <div>
                            <span className="font-medium">CMS Article:</span>{" "}
                            {candidate.payload_article_id}
                          </div>
                        )}
                      </div>

                      {/* Admin notes & review info */}
                      {candidate.admin_notes && (
                        <div className="bg-muted/30 rounded p-3 text-sm">
                          <span className="font-medium text-foreground">
                            Admin notes:
                          </span>{" "}
                          <span className="text-muted-foreground">
                            {candidate.admin_notes}
                          </span>
                        </div>
                      )}

                      {/* Action buttons for pending candidates */}
                      {candidate.status === "pending" && (
                        <div className="space-y-3">
                          <textarea
                            placeholder="Admin notes (optional)"
                            value={noteInputs[candidate.id] || ""}
                            onChange={(e) =>
                              setNoteInputs((prev) => ({
                                ...prev,
                                [candidate.id]: e.target.value,
                              }))
                            }
                            className="w-full px-3 py-2 border rounded-md bg-background text-foreground text-sm resize-none h-16"
                          />
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => handleApprove(candidate.id)}
                              disabled={actionLoading === candidate.id}
                              className="bg-green-700 hover:bg-green-800 text-white"
                            >
                              {actionLoading === candidate.id
                                ? "..."
                                : "Approve"}
                            </Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => handleReject(candidate.id)}
                              disabled={actionLoading === candidate.id}
                            >
                              {actionLoading === candidate.id
                                ? "..."
                                : "Reject"}
                            </Button>
                          </div>
                        </div>
                      )}

                      {/* Publish button for approved candidates */}
                      {candidate.status === "approved" && (
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => handlePublish(candidate.id)}
                            disabled={actionLoading === candidate.id}
                            className="bg-blue-700 hover:bg-blue-800 text-white"
                          >
                            {actionLoading === candidate.id
                              ? "Publishing..."
                              : "Publish as CMS Draft"}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Pagination */}
              {total > limit && (
                <div className="flex justify-between items-center pt-4">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    disabled={offset === 0}
                  >
                    Previous
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    Page {Math.floor(offset / limit) + 1} of{" "}
                    {Math.ceil(total / limit)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setOffset(offset + limit)}
                    disabled={offset + limit >= total}
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
