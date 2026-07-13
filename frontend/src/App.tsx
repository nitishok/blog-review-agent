import { useState } from "react";
import { getReview, Review, Ticket } from "./api";
import BlogReviewView from "./components/BlogReviewView";
import Queue from "./components/Queue";
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

  const handleBack = () => {
    setSelectedTicket(null);
    setReview(null);
    setReviewError(null);
  };

  if (review) {
    return <BlogReviewView review={review} onBack={handleBack} />;
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="app-title">Marketing Review Queue</h1>
        <Queue onSelect={handleSelectTicket} selectedId={selectedTicket?.id ?? null} />
      </aside>

      <main className="main-content">
        {!selectedTicket && (
          <div className="empty-state">Select a blog ticket to review</div>
        )}
        {selectedTicket && loadingReview && (
          <div className="empty-state">Loading review…</div>
        )}
        {selectedTicket && !loadingReview && reviewError && (
          <div className="empty-state error-state">Error: {reviewError}</div>
        )}
        {selectedTicket && !loadingReview && !reviewError && !review && (
          <div className="empty-state">Review is being generated, check back in a moment…</div>
        )}
      </main>
    </div>
  );
}
