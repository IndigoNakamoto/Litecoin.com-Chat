"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { apiUrl } from "@/lib/apiBase";
import TopicPicker from "@/components/landing/TopicPicker";
import QuestionGrid from "@/components/landing/QuestionGrid";
import type { LandingCategory, LandingData, LandingQuestion, QuestionClickMeta } from "@/components/landing/types";

interface SuggestedQuestionsProps {
  onQuestionClick: (question: string, metadata?: QuestionClickMeta) => void;
  onQuestionsLoaded?: (questions: LandingQuestion[]) => void;
}

/** Shown only when the backend endpoint itself is unreachable. */
const FALLBACK_QUESTIONS: LandingQuestion[] = [
  { id: "1", question: "What is Litecoin and how does it differ from Bitcoin?", order: 0, isActive: true },
  { id: "2", question: "How do I buy Litecoin?", order: 1, isActive: true },
  { id: "3", question: "What are the benefits of Litecoin's faster transactions?", order: 2, isActive: true },
  { id: "4", question: "How does Litecoin mining work?", order: 3, isActive: true },
  { id: "5", question: "Does Litecoin have privacy features?", order: 4, isActive: true },
  { id: "6", question: "What are the scalability solutions for Litecoin?", order: 5, isActive: true },
];

/** Walk `parentId` links up to the top-level category (bounded, cycle-safe). */
function topLevelOf(categoryId: string, byId: Map<string, LandingCategory>): string {
  let current = categoryId;
  for (let i = 0; i < 6; i++) {
    const cat = byId.get(current);
    if (!cat || !cat.parentId || !byId.has(cat.parentId)) return current;
    current = cat.parentId;
  }
  return current;
}

/**
 * Landing experience: topic picker -> question grid.
 *
 * Data comes from `GET /api/v1/suggested-questions` (one request, via the app's
 * own `/api/v1/*` rewrite). If the CMS has no categories, or the request fails,
 * this degrades to the flat question grid the page always had.
 */
const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({ onQuestionClick, onQuestionsLoaded }) => {
  const [data, setData] = useState<LandingData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // undefined = topic picker; null = "All topics"; string = a category id
  const [selectedCategory, setSelectedCategory] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const res = await fetch(apiUrl("/api/v1/suggested-questions"), { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error(`Failed to load suggested questions (${res.status})`);
        const body = (await res.json()) as LandingData;
        if (cancelled) return;
        const safe: LandingData = {
          categories: Array.isArray(body.categories) ? body.categories : [],
          questions: Array.isArray(body.questions) ? body.questions : [],
          fallback: body.fallback,
        };
        setData(safe);
        onQuestionsLoaded?.(safe.questions);
      } catch (err) {
        if (cancelled) return;
        console.error("Error fetching suggested questions:", err);
        setError(err instanceof Error ? err.message : "Failed to load suggested questions");
        setData({ categories: [], questions: FALLBACK_QUESTIONS, fallback: true });
        onQuestionsLoaded?.(FALLBACK_QUESTIONS);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [onQuestionsLoaded]);

  const allQuestions = useMemo(() => data?.questions ?? [], [data]);
  const activeQuestions = useMemo(() => allQuestions.filter((q) => q.isActive), [allQuestions]);

  const categoryById = useMemo(() => {
    const m = new Map<string, LandingCategory>();
    (data?.categories ?? []).forEach((c) => m.set(c.id, c));
    return m;
  }, [data]);

  // Active question counts rolled up to the top-level category.
  const countsByTopCategory = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const q of activeQuestions) {
      if (!q.categoryId || !categoryById.has(q.categoryId)) continue;
      const top = topLevelOf(q.categoryId, categoryById);
      counts[top] = (counts[top] ?? 0) + 1;
    }
    return counts;
  }, [activeQuestions, categoryById]);

  // Top-level categories that actually have questions. If none do, there is no
  // picker to show: fall back to the flat grid.
  const topCategories = useMemo(
    () =>
      (data?.categories ?? [])
        .filter((c) => !c.parentId || !categoryById.has(c.parentId))
        .filter((c) => (countsByTopCategory[c.id] ?? 0) > 0)
        .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name)),
    [data, categoryById, countsByTopCategory],
  );
  const hasPicker = topCategories.length > 0;

  const visibleQuestions = useMemo(() => {
    if (!selectedCategory) return activeQuestions; // null (All topics) or undefined (no picker)
    return activeQuestions.filter(
      (q) => q.categoryId && categoryById.has(q.categoryId) && topLevelOf(q.categoryId, categoryById) === selectedCategory,
    );
  }, [activeQuestions, selectedCategory, categoryById]);

  const selectedCategoryObj = selectedCategory ? categoryById.get(selectedCategory) ?? null : null;

  const handleQuestion = useCallback(
    (q: LandingQuestion, extra?: Partial<QuestionClickMeta>) => {
      const catId = q.categoryId && categoryById.has(q.categoryId) ? topLevelOf(q.categoryId, categoryById) : selectedCategory ?? null;
      const catName = catId ? categoryById.get(catId)?.name ?? null : null;
      onQuestionClick(q.question, { categoryId: catId, categoryName: catName, ...extra });
    },
    [categoryById, onQuestionClick, selectedCategory],
  );

  // "I'm Feeling Lit" draws from the whole pool (active + inactive, as before),
  // scoped to the current category when one is selected.
  const handleFeelingLit = useCallback(() => {
    let pool = allQuestions;
    if (selectedCategory) {
      const scoped = allQuestions.filter(
        (q) => q.categoryId && categoryById.has(q.categoryId) && topLevelOf(q.categoryId, categoryById) === selectedCategory,
      );
      if (scoped.length > 0) pool = scoped;
    }
    if (pool.length === 0) return;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    handleQuestion(pick, { fromFeelingLit: true, originalQuestion: pick.question });
  }, [allQuestions, selectedCategory, categoryById, handleQuestion]);

  if (isLoading) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-6">
          <h2 className="font-space-grotesk text-[30px] font-semibold text-foreground mb-2">Get started with Litecoin</h2>
          <p className="text-lg text-muted-foreground">Loading questions...</p>
        </div>
      </div>
    );
  }

  if (activeQuestions.length === 0 && !error) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-6">
          <h2 className="font-space-grotesk text-[30px] font-semibold text-foreground mb-2">Get started with Litecoin</h2>
          <p className="text-lg text-muted-foreground">No suggested questions available</p>
        </div>
      </div>
    );
  }

  const showPicker = hasPicker && selectedCategory === undefined;

  return (
    <AnimatePresence mode="wait" initial={false}>
      {showPicker ? (
        <motion.div
          key="picker"
          className="w-full"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
        >
          <TopicPicker
            categories={topCategories}
            totalQuestions={activeQuestions.length}
            countsByCategory={countsByTopCategory}
            onSelect={(id) => setSelectedCategory(id)}
            onFeelingLit={allQuestions.length > 0 ? handleFeelingLit : undefined}
          />
        </motion.div>
      ) : (
        <motion.div
          key={`grid-${selectedCategory ?? "all"}`}
          className="w-full"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
        >
          <QuestionGrid
            title={selectedCategoryObj ? `${selectedCategoryObj.icon ? `${selectedCategoryObj.icon} ` : ""}${selectedCategoryObj.name}` : "Get started with Litecoin"}
            subtitle={selectedCategoryObj?.description || undefined}
            questions={visibleQuestions}
            resetKey={selectedCategory ?? "all"}
            onQuestionClick={(q) => handleQuestion(q)}
            onBack={hasPicker ? () => setSelectedCategory(undefined) : undefined}
            onFeelingLit={allQuestions.length > 0 ? handleFeelingLit : undefined}
            error={error}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default SuggestedQuestions;
