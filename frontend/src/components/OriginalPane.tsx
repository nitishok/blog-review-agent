interface Props {
  text: string;
}

export default function OriginalPane({ text }: Props) {
  const paragraphs = text.split(/\n\n+/).filter(Boolean);

  return (
    <div className="doc-pane original-pane">
      <div className="pane-label">Original</div>
      <div className="pane-body">
        {paragraphs.map((p, i) => (
          <p key={i} className="doc-para">{p}</p>
        ))}
      </div>
    </div>
  );
}
