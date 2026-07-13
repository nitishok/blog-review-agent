import { SuggestionState } from "./BlogReviewView";

interface Props {
  suggestions: SuggestionState[];
  onApprove: () => void;
  submitting: boolean;
  error: string | null;
}

export default function ApproveBar({ suggestions, onApprove, submitting, error }: Props) {
  const accepted = suggestions.filter(s => s.status === "accepted").length;
  const rejected = suggestions.filter(s => s.status === "rejected").length;
  const pending  = suggestions.filter(s => s.status === "pending").length;

  return (
    <div className="approve-bar">
      <div className="approve-counts">
        <span className="count accepted">{accepted} accepted</span>
        <span className="count-sep">·</span>
        <span className="count rejected">{rejected} rejected</span>
        <span className="count-sep">·</span>
        <span className="count pending">{pending} pending</span>
      </div>
      {error && <span className="approve-error">{error}</span>}
      <button
        className="approve-btn"
        onClick={onApprove}
        disabled={submitting || accepted === 0}
      >
        {submitting ? "Sending..." : "Approve & Send Back"}
      </button>
    </div>
  );
}
