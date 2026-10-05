/** Shapes returned by GET /api/v1/suggested-questions (see backend/api/v1/suggested_questions.py). */

export type AudienceLevel = "beginner" | "intermediate" | "advanced";

export interface LandingCategory {
  id: string;
  name: string;
  description?: string | null;
  icon?: string | null;
  audienceLevel?: AudienceLevel | string | null;
  order: number;
  parentId?: string | null;
  /** Active questions assigned directly to this category (server-side count). */
  questionCount: number;
}

export interface LandingQuestion {
  id: string;
  question: string;
  order: number;
  isActive: boolean;
  categoryId?: string | null;
  /** A pre-generated answer exists; this question will answer instantly. */
  cached?: boolean;
}

export interface LandingData {
  categories: LandingCategory[];
  questions: LandingQuestion[];
  fallback?: boolean;
}

/** Metadata passed up with a question click so the chat can carry a topic hint. */
export interface QuestionClickMeta {
  fromFeelingLit?: boolean;
  originalQuestion?: string;
  categoryId?: string | null;
  categoryName?: string | null;
}
