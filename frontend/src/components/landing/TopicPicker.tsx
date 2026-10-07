"use client";

import React from "react";
import { motion } from "framer-motion";
import { Flame, ArrowRight } from "lucide-react";
import type { LandingCategory } from "./types";

interface TopicPickerProps {
  categories: LandingCategory[];
  /** Active questions across all categories (for the "All topics" card). */
  totalQuestions: number;
  /** Count of active questions under each top-level category (sub-categories rolled up). */
  countsByCategory: Record<string, number>;
  onSelect: (categoryId: string | null) => void;
  onFeelingLit?: () => void;
}

const AUDIENCE_LABEL: Record<string, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

const AUDIENCE_CLASS: Record<string, string> = {
  beginner: "bg-emerald-400/10 text-emerald-200 border-emerald-400/40",
  intermediate: "bg-sky-400/10 text-sky-200 border-sky-400/40",
  advanced: "bg-violet-400/10 text-violet-200 border-violet-400/40",
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.28, ease: [0.4, 0, 0.2, 1] as const } },
};

function AudienceBadge({ level }: { level?: string | null }) {
  if (!level || !AUDIENCE_LABEL[level]) return null;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${AUDIENCE_CLASS[level]}`}>
      {AUDIENCE_LABEL[level]}
    </span>
  );
}

/**
 * Step 1 of the landing page: pick a topic. Categories come from the CMS
 * (`categories` collection, shared with Articles); "All topics" keeps the old
 * flat list one click away.
 */
export default function TopicPicker({
  categories,
  totalQuestions,
  countsByCategory,
  onSelect,
  onFeelingLit,
}: TopicPickerProps) {
  return (
    <div className="w-full max-w-5xl mx-auto px-4 py-8 relative z-10" data-testid="topic-picker">
      <div className="text-center mb-8">
        <h2 className="font-space-grotesk text-[32px] md:text-[36px] font-bold mb-3 bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text text-transparent">
          Get started with Litecoin
        </h2>
        <p className="text-lg text-muted-foreground">Pick a topic, or ask anything below</p>
      </div>

      <motion.div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-fr"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={itemVariants} className="flex" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="group w-full h-full p-5 text-left rounded-xl border border-primary/30 bg-primary/5 hover:bg-primary/10 hover:border-primary/60 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 flex flex-col gap-3"
            aria-label="Browse all topics"
            data-testid="topic-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-base font-semibold text-card-foreground group-hover:text-primary">All topics</div>
                <div className="text-sm text-muted-foreground mt-1">Every suggested question in one list</div>
              </div>
              <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-transform" aria-hidden />
            </div>
            <div className="mt-auto text-xs text-muted-foreground">{totalQuestions} questions</div>
          </button>
        </motion.div>

        {categories.map((cat) => {
          const count = countsByCategory[cat.id] ?? cat.questionCount ?? 0;
          return (
            <motion.div key={cat.id} variants={itemVariants} className="flex" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <button
                type="button"
                onClick={() => onSelect(cat.id)}
                className="group w-full h-full p-5 text-left rounded-xl border border-border bg-card hover:bg-accent/5 hover:border-primary/60 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 flex flex-col gap-3"
                aria-label={`Browse ${cat.name} questions`}
                data-testid={`topic-${cat.id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold text-card-foreground group-hover:text-primary">{cat.name}</div>
                    {cat.description ? (
                      <div className="text-sm text-muted-foreground mt-1 line-clamp-2">{cat.description}</div>
                    ) : null}
                  </div>
                  <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-transform" aria-hidden />
                </div>
                <div className="mt-auto flex items-center justify-between gap-2">
                  <AudienceBadge level={cat.audienceLevel} />
                  <span className="text-xs text-muted-foreground ml-auto">
                    {count} {count === 1 ? "question" : "questions"}
                  </span>
                </div>
              </button>
            </motion.div>
          );
        })}
      </motion.div>

      {onFeelingLit && totalQuestions > 0 && (
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
