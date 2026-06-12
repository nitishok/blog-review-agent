import { useState } from "react";
import { getReview, Review, Ticket } from "./api";
import Queue from "./components/Queue";
import ReviewPane from "./components/ReviewPane";
import "./App.css";

export default function App() {
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [loadingReview, setLoadingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const handleSelectTicket = async (ticket: Ticket) => {
    setSelectedTicket(ticket);
    setReview(null);
    setReviewError(null);
    if (!ticket.review_ready) return;
    setLoadingReview(true);
    try {
      const r = await getReview(ticket.id);
      setReview(r);
    } catch (e: any) {
      setReviewError(e?.response?.data?.detail || "Failed to load review");
    } finally {
      setLoadingReview(false);
    }
  };

  const handleApproved = () => {
    setSelectedTicket(null);
    setReview(null);
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="app-title">CEO Review Queue</h1>
        <Queue onSelect={handleSelectTicket} selectedId={selectedTicket?.id ?? null} />
      </aside>

      <main className="main-content">
        {!selectedTicket && (
          <div className="empty-state">Select a ticket to review</div>
        )}
        {selectedTicket && !review && !loadingReview && (
          <div className="empty-state">
            {reviewError
              ? `Error: ${reviewError}`
              : "Review is being generated, check back in a moment..."}
          </div>
        )}
        {loadingReview && <div className="empty-state">Loading review...</div>}
        {review && (
          <ReviewPane review={review} onApproved={handleApproved} />
        )}
      </main>
    </div>
  );
}
