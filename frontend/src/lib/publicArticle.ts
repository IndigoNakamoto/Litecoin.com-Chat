/**
 * Server-side loader for the public article reader (/chat/articles/[id]).
 *
 * Reads a published article from Payload's REST API. Payload's `articleReadAccess`
 * already restricts anonymous reads to `status: published`, so a draft id yields
 * 403/404 and we render not-found. Inside Docker we call the service name
 * (PAYLOAD_INTERNAL_URL); locally we fall back to the public CMS host.
 */

export interface PublicArticle {
  id: string;
  title: string;
  markdown: string;
  sourceUrl?: string | null;
  sourceTier?: string | null;
  updatedAt?: string | null;
  publishedDate?: string | null;
  lastReviewedAt?: string | null;
}

function payloadBase(): string {
  return (
    process.env.PAYLOAD_INTERNAL_URL?.trim() ||
    process.env.NEXT_PUBLIC_PAYLOAD_URL?.trim() ||
    "https://cms.lite.space"
  ).replace(/\/$/, "");
}

function localized(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const v = value as Record<string, unknown>;
    const en = v.en;
    if (typeof en === "string") return en;
    const first = Object.values(v).find((x) => typeof x === "string");
    if (typeof first === "string") return first;
  }
  return "";
}

const ID_RE = /^[a-f0-9]{24}$/i;

export async function fetchPublicArticle(id: string): Promise<PublicArticle | null> {
  if (!ID_RE.test(id)) return null;
  try {
    const res = await fetch(`${payloadBase()}/api/articles/${id}?depth=0&locale=en`, {
      headers: { Accept: "application/json" },
      // Articles change rarely; revalidate every 5 minutes so an edit shows up without a redeploy.
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    const doc = (await res.json()) as Record<string, unknown>;
    if (!doc || doc.status !== "published") return null;
    const markdown = typeof doc.markdown === "string" ? doc.markdown : "";
    const title = localized(doc.title) || "Untitled";
    if (!markdown) return null;
    return {
      id: String(doc.id ?? id),
      title,
      markdown,
      sourceUrl: typeof doc.sourceUrl === "string" ? doc.sourceUrl : null,
      sourceTier: typeof doc.sourceTier === "string" ? doc.sourceTier : null,
      updatedAt: typeof doc.updatedAt === "string" ? doc.updatedAt : null,
      publishedDate: typeof doc.publishedDate === "string" ? doc.publishedDate : null,
      lastReviewedAt: typeof doc.lastReviewedAt === "string" ? doc.lastReviewedAt : null,
    };
  } catch (e) {
    console.error("fetchPublicArticle failed", e);
    return null;
  }
}
