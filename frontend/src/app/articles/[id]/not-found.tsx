import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function ArticleNotFound() {
  return (
    <main className="mx-auto my-24 w-full max-w-3xl rounded-2xl border border-border bg-card px-4 py-16 sm:px-6">
      <h1 className="font-space-grotesk text-[28px] font-semibold text-foreground">Article not available</h1>
      <p className="mt-3 text-foreground/80">
        This article is not published, or the link is out of date. The knowledge base is edited continuously; the
        chat always cites the current version.
      </p>
      <Link href="/" className="mt-6 inline-flex items-center gap-1.5 text-sm text-primary hover:text-primary/80">
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to chat
      </Link>
    </main>
  );
}
