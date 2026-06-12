import { useEffect, useState } from "react";
import { getQueue, Ticket } from "../api";

interface Props {
  onSelect: (ticket: Ticket) => void;
  selectedId: string | null;
}

export default function Queue({ onSelect, selectedId }: Props) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      getQueue()
        .then(setTickets)
        .finally(() => setLoading(false));
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="queue-loading">Loading queue...</div>;
  if (tickets.length === 0)
    return <div className="queue-empty">No tickets in CEO Review</div>;

  return (
    <ul className="queue-list">
      {tickets.map((t) => (
        <li
          key={t.id}
          className={`queue-item ${selectedId === t.id ? "selected" : ""}`}
          onClick={() => onSelect(t)}
        >
          <span className="ticket-id">{t.id}</span>
          <span className="ticket-summary">{t.summary}</span>
          <span className={`review-badge ${t.review_ready ? "ready" : "pending"}`}>
            {t.review_ready ? "Ready" : "Generating..."}
          </span>
        </li>
      ))}
    </ul>
  );
}
