import CommentBubble from "./CommentBubble";
import { SuggestionState } from "./BlogReviewView";

interface Props {
  text: string;
  suggestions: SuggestionState[];
  onUpdate: (index: number, value: string) => void;
  onAccept: (index: number) => void;
  onReject: (index: number) => void;
  onUndo: (index: number) => void;
}

export default function SuggestedPane({ text, suggestions, onUpdate, onAccept, onReject, onUndo }: Props) {
  const paragraphs = text.split(/\n\n+/).filter(Boolean);

  // Map each paragraph to the first suggestion whose original_text appears in it
  const findSuggestion = (para: string): { suggestion: SuggestionState; index: number } | null => {
    for (let i = 0; i < suggestions.length; i++) {
      if (para.includes(suggestions[i].original_text)) {
        return { suggestion: suggestions[i], index: i };
      }
    }
    return null;
  };

  const renderParaText = (para: string, match: { suggestion: SuggestionState; index: number } | null) => {
    if (!match) return <>{para}</>;
    const { suggestion, index } = match;
    const { original_text, suggestion: suggestedText, status } = suggestion;

    const before = para.slice(0, para.indexOf(original_text));
    const after  = para.slice(para.indexOf(original_text) + original_text.length);

    const highlightClass = status === "rejected"
      ? "suggestion-text rejected"
      : status === "accepted"
      ? "suggestion-text accepted"
      : "suggestion-text pending";

    return (
      <>
        {before}
        <span className={highlightClass}>
          {status === "rejected" ? original_text : suggestedText}
        </span>
        {after}
      </>
    );
  };

  return (
    <div className="doc-pane suggested-pane">
      <div className="pane-label">Suggested</div>
      <div className="pane-body">
        {paragraphs.map((para, i) => {
          const match = findSuggestion(para);
          return (
            <div key={i} className="suggested-row">
              <p className="doc-para suggested-para">
                {renderParaText(para, match)}
              </p>
              <div className="bubble-slot">
                {match && (
                  <CommentBubble
                    suggestion={match.suggestion}
                    index={match.index}
                    onUpdate={onUpdate}
                    onAccept={onAccept}
                    onReject={onReject}
                    onUndo={onUndo}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
