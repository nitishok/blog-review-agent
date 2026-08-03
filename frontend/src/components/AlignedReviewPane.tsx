import { Block } from "../api";
import CommentBubble from "./CommentBubble";
import { SuggestionState } from "./BlogReviewView";

interface Props {
  text: string;
  blocks: Block[];
  suggestions: SuggestionState[];
  onUpdate: (index: number, value: string) => void;
  onAccept: (index: number) => void;
  onReject: (index: number) => void;
  onUndo: (index: number) => void;
}

export default function AlignedReviewPane({ text, blocks, suggestions, onUpdate, onAccept, onReject, onUndo }: Props) {
  // Fall back to splitting original_text if no blocks provided
  const rows: Block[] = blocks && blocks.length > 0
    ? blocks
    : text.split(/\n\n+/).filter(Boolean).map(t => ({ type: "paragraph" as const, text: t }));

  const findSuggestion = (para: string): { suggestion: SuggestionState; index: number } | null => {
    for (let i = 0; i < suggestions.length; i++) {
      if (para.includes(suggestions[i].original_text)) return { suggestion: suggestions[i], index: i };
    }
    return null;
  };

  const renderSuggested = (para: string, match: { suggestion: SuggestionState; index: number } | null) => {
    if (!match) return <>{para}</>;
    const { suggestion } = match;
    const { original_text, suggestion: suggestedText, status } = suggestion;
    const before = para.slice(0, para.indexOf(original_text));
    const after  = para.slice(para.indexOf(original_text) + original_text.length);
    return (
      <>
        {before}
        <span className={`redline-del${status === "accepted" ? " accepted" : ""}`}>{original_text}</span>
        {status !== "rejected" && (
          <> <span className={`redline-ins${status === "accepted" ? " accepted" : ""}`}>{suggestedText}</span></>
        )}
        {after}
      </>
    );
  };

  return (
    <div className="aligned-review">
      {/* Sticky column headers */}
      <div className="aligned-headers">
        <div className="aligned-col-header">Original</div>
        <div className="aligned-col-header">Suggested</div>
      </div>

      {rows.map((block, i) => {
        if (block.type === "image") {
          return (
            <div key={i} className="aligned-row aligned-image-row">
              <div className="aligned-left">
                <img src={block.src} alt={block.alt || ""} className="doc-image" />
              </div>
              <div className="aligned-right">
                <img src={block.src} alt={block.alt || ""} className="doc-image" />
              </div>
            </div>
          );
        }

        const para = block.text || "";
        const match = findSuggestion(para);
        return (
          <div key={i} className={`aligned-row${match ? " has-suggestion" : ""}`}>
            {/* Left: original */}
            <div className="aligned-left">
              <p className="doc-para">{para}</p>
            </div>

            {/* Right: suggested text + bubble */}
            <div className="aligned-right">
              <p className="doc-para aligned-suggested-para">
                {renderSuggested(para, match)}
              </p>
              {match && (
                <div className="aligned-bubble">
                  <CommentBubble
                    suggestion={match.suggestion}
                    index={match.index}
                    onUpdate={onUpdate}
                    onAccept={onAccept}
                    onReject={onReject}
                    onUndo={onUndo}
                  />
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
