"use client";

import React from "react";
import { Button } from "@/components/ui/button";

interface FollowUpQuestionsProps {
  questions: string[];
  onQuestionClick: (question: string) => void;
}

const FollowUpQuestions: React.FC<FollowUpQuestionsProps> = ({
  questions,
  onQuestionClick,
}) => {
  if (!questions.length) {
    return null;
  }

  return (
    <div className="mt-6 mb-2 min-w-0">
      <p className="text-sm font-medium text-foreground mb-3">Ask next</p>
      <div className="flex min-w-0 flex-wrap gap-2">
        {questions.map((question) => (
          <Button
            key={question}
            type="button"
            variant="outline"
            size="sm"
            className="h-auto max-w-full min-w-0 shrink justify-start whitespace-normal break-words rounded-full py-2 text-left leading-snug"
            onClick={() => onQuestionClick(question)}
          >
            {question}
          </Button>
        ))}
      </div>
    </div>
  );
};

export default FollowUpQuestions;
