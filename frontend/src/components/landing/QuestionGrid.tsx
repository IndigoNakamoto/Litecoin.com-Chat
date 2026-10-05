"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, ChevronRight, Flame, Zap } from "lucide-react";
import type { LandingQuestion } from "./types";

interface QuestionGridProps {
  title: string;
  subtitle?: string;
  questions: LandingQuestion[];
  onQuestionClick: (question: LandingQuestion) => void;
  onBack?: () => void;
  onFeelingLit?: () => void;
  /** Reset pagination when the set of questions changes (e.g. category switch). */
  resetKey?: string;
  error?: string | null;
}

const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return isMobile;
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.4, 0, 0.2, 1] as const } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.2 } },
};

/**
 * Step 2 of the landing page (and the whole landing page when the CMS has no
 * categories): the question grid with "Show me more" pagination.
 */
export default function QuestionGrid({
  title,
  subtitle,
  questions,
  onQuestionClick,
  onBack,
  onFeelingLit,
  resetKey,
  error,
}: QuestionGridProps) {
  const isMobile = useIsMobile();
  const [currentPage, setCurrentPage] = useState(0);

  useEffect(() => {
    setCurrentPage(0);
  }, [resetKey]);

  const QUESTIONS_PER_PAGE = isMobile ? 3 : 7;
  const endIndex = (currentPage + 1) * QUESTIONS_PER_PAGE;
  const visible = questions.slice(0, endIndex);
  const hasMore = endIndex < questions.length;

  return (
    <div className="w-full max-w-4xl mx-auto px-4 py-8 relative z-10" data-testid="question-grid">
      <div className="text-center mb-8 relative">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="absolute left-0 top-1 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary transition-colors focus:outline-none focus:ring-2 focus:ring-primary/50 rounded-md px-1"
            aria-label="Back to topics"
            data-testid="back-to-topics"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">Topics</span>
          </button>
        )}
        <h2 className="font-space-grotesk text-[32px] md:text-[36px] font-bold mb-3 bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text text-transparent">
          {title}
        </h2>
        <p className="text-lg text-muted-foreground">{subtitle || "Choose a question below or ask your own"}</p>
        {error && <p className="text-sm text-destructive mt-2">{error}</p>}
      </div>

      {questions.length === 0 ? (
        <div className="text-center text-muted-foreground py-6" data-testid="question-grid-empty">
          No questions here yet. Try another topic or ask your own below.
        </div>
      ) : (
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 gap-4 auto-rows-fr"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <AnimatePresence mode="popLayout">
            {visible.map((item) => (
              <motion.div
                key={item.id}
                variants={itemVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
                layout
                className="flex"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <button
                  type="button"
                  onClick={() => onQuestionClick(item)}
                  className="p-5 text-left bg-card border border-border rounded-xl hover:bg-accent/5 hover:border-primary/60 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300 group w-full h-full flex items-start justify-between gap-3 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2"
                  aria-label={`Ask: ${item.question}`}
                >
                  <span className="text-base font-semibold text-card-foreground group-hover:text-primary leading-relaxed">
                    {item.question}
                  </span>
                  {item.cached && (
                    <span
                      className="shrink-0 inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700"
                      title="Answers instantly"
                      data-testid="instant-badge"
                    >
                      <Zap className="h-3 w-3" aria-hidden />
                      Instant
                    </span>
                  )}
                </button>
              </motion.div>
            ))}
            {hasMore && (
              <motion.div
                key="show-more"
                variants={itemVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
                layout
                className="flex"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => p + 1)}
                  className="p-5 text-center bg-card/50 border border-border/50 rounded-xl hover:bg-accent/30 hover:border-primary/30 transition-all duration-300 group w-full h-full flex items-center justify-center gap-2 shadow-sm hover:shadow-xl hover:shadow-primary/10 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2"
                  aria-label="Show more questions"
                >
                  <span className="text-base font-medium text-muted-foreground group-hover:text-primary leading-relaxed">
                    Show me more
                  </span>
                  <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-transform duration-300" />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}

      {onFeelingLit && (
        <motion.div
          className="mt-8 flex justify-center"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.3 }}
        >
          <motion.button
            type="button"
            onClick={onFeelingLit}
            className="p-3 text-center bg-gradient-to-r from-primary to-primary/80 border border-primary/20 rounded-xl transition-all duration-300 group max-w-xs w-full shadow-lg hover:shadow-xl hover:shadow-primary/10 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 relative overflow-hidden"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <span className="text-base font-semibold text-white leading-relaxed flex items-center justify-center gap-2 relative z-10">
              <Flame className="h-4 w-4 group-hover:animate-fire-burst" />
              I&apos;m Feeling Lit
            </span>
          </motion.button>
        </motion.div>
      )}
    </div>
  );
}
