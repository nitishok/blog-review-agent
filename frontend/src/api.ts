import axios from "axios";

const api = axios.create({ baseURL: "http://localhost:8000" });

export interface Ticket {
  id: string;
  summary: string;
  status: string;
  assignee: string | null;
  updated: string;
  review_ready: boolean;
}

export interface Suggestion {
  original_text: string;
  suggestion: string;
  rationale: string;
}

export interface Block {
  type: "paragraph" | "image";
  text?: string;
  src?: string;
  alt?: string;
}

export interface Review {
  ticket_id: string;
  ticket: Ticket;
  original_text: string;
  blocks: Block[];
  suggestions: Suggestion[];
  sharepoint_url: string;
}

export const getQueue = (): Promise<Ticket[]> =>
  api.get("/queue").then((r) => r.data);

export const getReview = (ticketId: string): Promise<Review> =>
  api.get(`/review/${ticketId}`).then((r) => r.data);

export const approve = (ticketId: string, finalSuggestions: Suggestion[]) =>
  api
    .post("/approve", { ticket_id: ticketId, final_suggestions: finalSuggestions })
    .then((r) => r.data);
