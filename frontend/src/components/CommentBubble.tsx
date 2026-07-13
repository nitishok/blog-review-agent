import { SuggestionState } from "./BlogReviewView";

interface Props {
  suggestion: SuggestionState;
  index: number;
  onUpdate: (index: number, value: string) => void;
  onAccept: (index: number) => void;
  onReject: (index: number) => void;
  onUndo: (index: number) => void;
}

export default function CommentBubble({ suggestion, index, onUpdate, onAccept, onReject, onUndo }: Props) {
  const { status, suggestion: text, rationale } = suggestion;

  return (
    <div className={`comment-bubble status-${status}`}>
      <div className="bubble-rationale">{rationale}</div>

      {status === "pending" && (
        <>
          <textarea
            className="bubble-edit"
            value={text}
            rows={2}
            onChange={e => onUpdate(index, e.target.value)}
            placeholder="Edit suggestion…"
          />
          <div className="bubble-actions">
            <button className="bubble-accept" onClick={() => onAccept(index)}>✓ Accept</button>
            <button className="bubble-reject" onClick={() => onReject(index)}>✕ Reject</button>
          </div>
        </>
      )}

      {status === "accepted" && (
        <div className="bubble-actions">
          <span className="bubble-status-label accepted">Accepted ✓</span>
          <button className="bubble-undo" onClick={() => onUndo(index)}>Undo</button>
        </div>
      )}

      {status === "rejected" && (
        <div className="bubble-actions">
          <span className="bubble-status-label rejected">Rejected</span>
          <button className="bubble-undo" onClick={() => onUndo(index)}>Undo</button>
        </div>
      )}
    </div>
  );
}
