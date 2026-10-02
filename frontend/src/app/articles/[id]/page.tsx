import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ArrowLeft, ExternalLink, Clock } from "lucide-react";
import ArticleMarkdown from "@/components/ArticleMarkdown";
import { fetchPublicArticle } from "@/lib/publicArticle";

/**
 * Public reader for a knowledge-base article: the target of source chips for
 * editor-authored content that has no external origin. Server-rendered from
 * Payload's REST API (published articles only).
 */

type Params = { id: string };

function fmt(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

function stripLeadingTitle(markdown: string, title: string): string {
  const lines = markdown.split("\n");
  const first = lines.findIndex((l) => l.trim() !== "");
  if (first >= 0 && /^#\s+/.test(lines[first]) && lines[first].replace(/^#\s+/, "").trim() === title.trim()) {
    return lines.slice(first + 1).join("\n").trimStart();
  }
  return markdown;
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { id } = await params;
  const article = await fetchPublicArticle(id);
  if (!article) return { title: "Article not found - Litecoin Knowledge Hub" };
  return {
    title: `${article.title} - Litecoin Knowledge Hub`,
    description: article.markdown.replace(/[#*_`>\-]/g, "").slice(0, 160),
    alternates: { canonical: `/articles/${article.id}` },
  };
}

export default async function ArticlePage({ params }: { params: Promise<Params> }) {
  const { id } = await params;
  const article = await fetchPublicArticle(id);
  if (!article) notFound();

  const updated = fmt(article.updatedAt);
  const reviewed = fmt(article.lastReviewedAt);
  const sourceHost = (() => {
    try {
      return article.sourceUrl ? new URL(article.sourceUrl).hostname.replace(/^www\./, "") : null;
    } catch {
      return null;
    }
  })();

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800">
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to chat
      </Link>

      <header className="mt-6 border-b border-border pb-4">
        <h1 className="font-space-grotesk text-[34px] font-semibold leading-tight text-[#222222]">{article.title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
          <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-blue-900">
            {article.sourceTier === "pinned" ? "Reference document" : "Litecoin Knowledge Hub"}
          </span>
          {updated ? (
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" aria-hidden />
              Updated {updated}
            </span>
          ) : null}
          {reviewed ? <span>Last reviewed {reviewed}</span> : null}
          {article.sourceUrl ? (
            <a
              href={article.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800"
            >
              Original source{sourceHost ? ` (${sourceHost})` : ""}
              <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          ) : null}
        </div>
      </header>

      <article className="mt-2">
        <ArticleMarkdown markdown={stripLeadingTitle(article.markdown, article.title)} />
      </article>

      <footer className="mt-10 border-t border-border pt-4 text-xs text-gray-500">
        This article is part of the Litecoin Knowledge Hub, the sourced knowledge base behind{" "}
        <Link href="/" className="text-blue-600 hover:text-blue-800">
          Litecoin Chat
        </Link>
        . Found something out of date? Use the thumbs-down on any answer that cites it.
      </footer>
    </main>
  );
}
