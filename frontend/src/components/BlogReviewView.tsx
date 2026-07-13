import { useState } from "react";
import { approve, Review } from "../api";
import ApproveBar from "./ApproveBar";
import OriginalPane from "./OriginalPane";
import SplitPane from "./SplitPane";
import SuggestedPane from "./SuggestedPane";
import TopBar from "./TopBar";

export interface SuggestionState {
  original_text: string;
  suggestion: string;
  rationale: string;
  status: "pending" | "accepted" | "rejected";
}

interface Props {
  review: Review;
  onBack: () => void;
}

export default function BlogReviewView({ review, onBack }: Props) {
  const [suggestions, setSuggestions] = useState<SuggestionState[]>(
    review.suggestions.map(s => ({ ...s, status: "pending" }))
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateSuggestion = (index: number, value: string) => {
    setSuggestions(prev =>
      prev.map((s, i) => i === index ? { ...s, suggestion: value } : s)
    );
  };

  const acceptSuggestion = (index: number) => {
    setSuggestions(prev =>
      prev.map((s, i) => i === index ? { ...s, status: "accepted" } : s)
    );
  };

  const rejectSuggestion = (index: number) => {
    setSuggestions(prev =>
      prev.map((s, i) => i === index ? { ...s, status: "rejected" } : s)
    );
  };

  const undoSuggestion = (index: number) => {
    setSuggestions(prev =>
      prev.map((s, i) => i === index ? { ...s, status: "pending" } : s)
    );
  };

  const handleApprove = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const accepted = suggestions
        .filter(s => s.status === "accepted")
        .map(({ original_text, suggestion, rationale }) => ({ original_text, suggestion, rationale }));
      await approve(review.ticket_id, accepted);
      onBack();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Approval failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="blog-review-view">
      <TopBar
        summary={review.ticket.summary}
        ticketId={review.ticket_id}
        sharepointUrl={review.sharepoint_url}
        onBack={onBack}
      />

      <div className="review-body">
        <SplitPane
          left={<OriginalPane text={review.original_text} />}
          right={
            <SuggestedPane
              text={review.original_text}
              suggestions={suggestions}
              onUpdate={updateSuggestion}
              onAccept={acceptSuggestion}
              onReject={rejectSuggestion}
              onUndo={undoSuggestion}
            />
          }
        />
      </div>

      <ApproveBar
        suggestions={suggestions}
        onApprove={handleApprove}
        submitting={submitting}
        error={error}
      />
    </div>
  );
}
