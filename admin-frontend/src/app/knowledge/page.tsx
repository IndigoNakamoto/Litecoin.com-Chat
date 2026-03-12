"use client";

import { AuthGuard } from "@/components/AuthGuard";
import { KnowledgeCandidates } from "@/components/KnowledgeCandidates";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import { LogOut, ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function KnowledgePage() {
  const router = useRouter();

  const handleLogout = () => {
    authApi.logout();
    router.push("/");
  };

  return (
    <AuthGuard>
      <div className="min-h-screen bg-background">
        <header className="bg-card border-b border-border shadow-sm">
          <div className="container mx-auto px-4 py-4 flex justify-between items-center">
            <div className="flex items-center gap-4">
              <Link href="/dashboard">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back to Dashboard
                </Button>
              </Link>
              <h1 className="text-2xl font-bold text-card-foreground">
                Knowledge Gap Review
              </h1>
            </div>
            <Button variant="outline" onClick={handleLogout}>
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </header>
        <main className="container mx-auto px-4 py-8">
          <KnowledgeCandidates />
        </main>
      </div>
    </AuthGuard>
  );
}
