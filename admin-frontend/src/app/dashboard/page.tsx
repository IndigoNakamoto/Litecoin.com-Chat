"use client";

import { AuthGuard } from "@/components/AuthGuard";
import { Dashboard } from "@/components/Dashboard";
import { BansThrottles } from "@/components/BansThrottles";
import { AbusePreventionSettings } from "@/components/AbusePreventionSettings";
import { SuggestedQuestionsCache } from "@/components/SuggestedQuestionsCache";
import { ResponseCacheManager } from "@/components/ResponseCacheManager";
import { UserStatistics } from "@/components/UserStatistics";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import { LogOut, FileText, Lightbulb } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
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
            <h1 className="text-2xl font-bold text-card-foreground">Admin Panel</h1>
            <div className="flex gap-2 items-center">
              <Link href="/knowledge">
                <Button variant="outline">
                  <Lightbulb className="h-4 w-4 mr-2" />
                  Knowledge Gaps
                </Button>
              </Link>
              <Link href="/questions">
                <Button variant="outline">
                  <FileText className="h-4 w-4 mr-2" />
                  Question Logs
                </Button>
              </Link>
              <Button variant="outline" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </header>
        <main className="container mx-auto px-4 py-8 space-y-8">
          <Dashboard />
          <UserStatistics />
          <AbusePreventionSettings />
          <BansThrottles />
          <ResponseCacheManager />
          <SuggestedQuestionsCache />
        </main>
      </div>
    </AuthGuard>
  );
}

