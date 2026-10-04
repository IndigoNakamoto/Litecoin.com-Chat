/**
 * Browser-side URL for a backend API path.
 *
 * The app is served under `basePath: '/chat'`, and Next's rewrite for
 * `/api/v1/*` is applied under that base path, so the correct request URL is
 * `${origin}/chat/api/v1/...` — a bare `/api/v1/...` 404s on the public host.
 * Mirrors `getChatApiBaseUrl` in app/page.tsx.
 */
export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  if (typeof window !== "undefined") {
    return `${window.location.origin}/chat${p}`;
  }
  return `${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"}${p}`;
}
