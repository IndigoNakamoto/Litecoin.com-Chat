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
    <div className="mt-6">
      <p className="text-sm font-medium text-gray-700 mb-3">Ask next</p>
      <div className="flex flex-wrap gap-2">
        {questions.map((question) => (
          <Button
            key={question}
            type="button"
            variant="outline"
            size="sm"
            className="rounded-full text-left h-auto whitespace-normal py-2"
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
