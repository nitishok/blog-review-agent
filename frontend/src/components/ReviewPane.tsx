import { useState } from "react";
import { approve, Review, Suggestion } from "../api";

interface Props {
  review: Review;
  onApproved: () => void;
}

export default function ReviewPane({ review, onApproved }: Props) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>(review.suggestions);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateSuggestion = (index: number, field: keyof Suggestion, value: string) => {
    setSuggestions((prev) =>
      prev.map((s, i) => (i === index ? { ...s, [field]: value } : s))
    );
  };

  const handleApprove = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await approve(review.ticket_id, suggestions);
      onApproved();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Approval failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="review-pane">
      <div className="review-header">
        <h2>{review.ticket.summary}</h2>
        <span className="ticket-meta">{review.ticket_id} · {review.sharepoint_url}</span>
      </div>

      <div className="suggestions-list">
        {suggestions.map((s, i) => (
          <div key={i} className="suggestion-card">
            <div className="suggestion-original">
              <label>Original</label>
              <blockquote>{s.original_text}</blockquote>
            </div>
            <div className="suggestion-right">
              <label>Suggested change</label>
              <textarea
                value={s.suggestion}
                onChange={(e) => updateSuggestion(i, "suggestion", e.target.value)}
                rows={3}
              />
              <label>Rationale</label>
              <input
                type="text"
                value={s.rationale}
                onChange={(e) => updateSuggestion(i, "rationale", e.target.value)}
              />
            </div>
          </div>
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="review-actions">
        <button
          className="approve-btn"
          onClick={handleApprove}
          disabled={submitting}
        >
          {submitting ? "Approving..." : "Approve & Send Back"}
        </button>
      </div>
    </div>
  );
}
