interface Props {
  summary: string;
  ticketId: string;
  sharepointUrl: string;
  onBack: () => void;
}

export default function TopBar({ summary, ticketId, sharepointUrl, onBack }: Props) {
  return (
    <div className="topbar">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <div className="topbar-title">
        <span className="topbar-ticket-id">{ticketId}</span>
        <span className="topbar-summary">{summary}</span>
      </div>
      <a
        className="topbar-sp-link"
        href={sharepointUrl}
        target="_blank"
        rel="noreferrer"
      >
        Open in SharePoint ↗
      </a>
    </div>
  );
}
