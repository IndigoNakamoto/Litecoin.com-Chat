"use client";

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cacheApi } from "@/lib/api";
import { CheckCircle2, AlertCircle, Trash2 } from "lucide-react";

interface ResponseCacheStats {
  query_cache: { size: number; max_size: number };
  semantic_cache: Record<string, any> | null;
}

export function ResponseCacheManager() {
  const [stats, setStats] = useState<ResponseCacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const fetchStats = async () => {
    try {
      const data = await cacheApi.getResponseStats();
      setStats(data);
    } catch (error) {
      setMessage({
        type: "error",
        text:
          error instanceof Error
            ? error.message
            : "Failed to load response cache stats",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleClear = async () => {
    setClearing(true);
    setMessage(null);
    try {
      const result = await cacheApi.clearResponseCaches();
      setMessage({ type: "success", text: result.message });
      setConfirmClear(false);
      await fetchStats();
    } catch (error) {
      setMessage({
        type: "error",
        text:
          error instanceof Error
            ? error.message
            : "Failed to clear response caches",
      });
      setConfirmClear(false);
    } finally {
      setClearing(false);
    }
  };

  const semanticSize =
    stats?.semantic_cache?.entries ??
    stats?.semantic_cache?.size ??
    0;

  if (loading) {
    return (
      <div className="text-center py-8 text-foreground">
        Loading response cache stats...
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Response Cache</CardTitle>
        <CardDescription>
          Cached question responses. Clearing forces fresh answers to be
          generated for all queries.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {message && (
          <div
            className={`flex items-center gap-2 p-3 rounded ${
              message.type === "success"
                ? "bg-green-50 text-green-800"
                : "bg-red-50 text-red-800"
            }`}
          >
            {message.type === "success" ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <AlertCircle className="h-4 w-4" />
            )}
            <span className="text-sm">{message.text}</span>
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="font-medium mb-2 text-card-foreground">
              Cache Statistics
            </h3>
            <div className="space-y-1 text-sm">
              <div>
                <span className="text-muted-foreground">
                  Query Cache (exact match):{" "}
                </span>
                <span className="font-medium text-card-foreground">
                  {stats?.query_cache?.size ?? 0} / {stats?.query_cache?.max_size ?? 0}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">
                  Semantic Cache:{" "}
                </span>
                <span className="font-medium text-card-foreground">
                  {stats?.semantic_cache
                    ? `${semanticSize} entries`
                    : "Not active"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-col justify-end">
            {confirmClear ? (
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  onClick={handleClear}
                  disabled={clearing}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {clearing ? "Clearing..." : "Confirm Clear"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setConfirmClear(false)}
                  disabled={clearing}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                variant="destructive"
                onClick={() => setConfirmClear(true)}
                disabled={clearing}
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Clear Response Caches
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
