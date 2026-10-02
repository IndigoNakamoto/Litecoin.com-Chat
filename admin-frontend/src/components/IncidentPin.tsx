"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { incidentApi, type IncidentPin as PinData } from "@/lib/api";
import { AlertTriangle, Pin, PinOff, RefreshCw } from "lucide-react";

/**
 * Incident override: one pinned answer that bypasses retrieval until cleared.
 * Use for a delisting, a Core release, or a scam wave.
 */
export function IncidentPin() {
  const [pin, setPin] = useState<PinData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [title, setTitle] = useState("");
  const [answer, setAnswer] = useState("");
  const [terms, setTerms] = useState("");
  const [ttl, setTtl] = useState("24");
  const [sourceTitle, setSourceTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      setPin(await incidentApi.get());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load incident pin");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const submit = async () => {
    if (!title.trim() || answer.trim().length < 10) {
      setError("Title and an answer of at least 10 characters are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const sources = sourceUrl.trim() ? [{ title: sourceTitle.trim() || sourceUrl.trim(), url: sourceUrl.trim() }] : [];
      const saved = await incidentApi.set({
        title: title.trim(),
        answer: answer.trim(),
        match_terms: terms.split(",").map((t) => t.trim()).filter(Boolean),
        ttl_hours: Math.max(0.25, Number(ttl) || 24),
        sources,
        created_by: "admin-dashboard",
      });
      setPin(saved);
      setShowForm(false);
      setTitle("");
      setAnswer("");
      setTerms("");
      setSourceTitle("");
      setSourceUrl("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to set incident pin");
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!confirm("Clear the incident pin? Normal retrieval resumes immediately.")) return;
    setSaving(true);
    try {
      await incidentApi.clear();
      setPin({ active: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear pin");
    } finally {
      setSaving(false);
    }
  };

  const active = pin?.active === true;

  return (
    <Card className={active ? "border-red-400/70 bg-red-50/40 dark:bg-red-950/20" : undefined}>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-card-foreground">
              {active ? <AlertTriangle className="h-5 w-5 text-red-600" /> : <Pin className="h-5 w-5" />}
              Incident Override
              {active && (
                <span className="ml-2 rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white">ACTIVE</span>
              )}
            </CardTitle>
            <CardDescription>
              One pinned answer served instead of retrieval until cleared or expired. For a delisting, a Core
              release, or a scam wave. Pinned answers are never cached.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

        {active && pin && (
          <div className="space-y-2 rounded-md border border-border bg-background p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold text-card-foreground">{pin.title}</div>
              <div className="text-xs text-muted-foreground">
                expires {pin.expires_at ? new Date(pin.expires_at).toLocaleString() : "?"} · id {pin.id}
              </div>
            </div>
            <div className="text-xs text-muted-foreground">
              Match: {pin.match_terms && pin.match_terms.length > 0 ? pin.match_terms.map((t) => `"${t}"`).join(", ") : "every question"}
            </div>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs text-card-foreground">{pin.answer}</pre>
            {pin.sources && pin.sources.length > 0 && (
              <div className="text-xs text-muted-foreground">
                Sources: {pin.sources.map((s) => s.url || s.title).join(", ")}
              </div>
            )}
            <div className="flex gap-2 pt-1">
              <Button variant="destructive" size="sm" onClick={clear} disabled={saving}>
                <PinOff className="mr-2 h-4 w-4" />
                Clear pin
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowForm((v) => !v)}>
                Replace
              </Button>
            </div>
          </div>
        )}

        {!active && !showForm && (
          <Button onClick={() => setShowForm(true)} variant="outline">
            <Pin className="mr-2 h-4 w-4" />
            Set an incident pin
          </Button>
        )}

        {showForm && (
          <div className="grid gap-3 rounded-md border border-border p-4">
            <div className="grid gap-1.5">
              <Label htmlFor="pin-title">Title (internal)</Label>
              <Input id="pin-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Exchange X delisting LTC" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="pin-answer">Pinned answer (markdown, shown to readers)</Label>
              <textarea
                id="pin-answer"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={6}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                placeholder="On <date>, Exchange X announced ... Here is what Litecoin holders should know ..."
              />
            </div>
            <div className="grid gap-1.5 md:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="pin-terms">Match terms (comma-separated; empty = every question)</Label>
                <Input id="pin-terms" value={terms} onChange={(e) => setTerms(e.target.value)} placeholder="exchange x, delist, delisting" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="pin-ttl">Expires after (hours)</Label>
                <Input id="pin-ttl" type="number" min={0.25} max={168} step={0.5} value={ttl} onChange={(e) => setTtl(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-1.5 md:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="pin-src-title">Source title (optional)</Label>
                <Input id="pin-src-title" value={sourceTitle} onChange={(e) => setSourceTitle(e.target.value)} placeholder="Official notice" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="pin-src-url">Source URL (optional)</Label>
                <Input id="pin-src-url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://..." />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={submit} disabled={saving}>
                <Pin className="mr-2 h-4 w-4" />
                {saving ? "Saving…" : active ? "Replace pin" : "Pin it"}
              </Button>
              <Button variant="ghost" onClick={() => setShowForm(false)} disabled={saving}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
