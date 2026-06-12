# CLAUDE.md — BlogReviewAgent

## App Name
This app is called **BlogReviewAgent**. Always use this name in commit messages, comments, and documentation. Never use "ReviewDesk", "CEO Review Agent", or any other name.

## What This Project Is

An AI-powered dashboard that emulates the CEO of an Appian-focused IT services company reviewing marketing content (blog posts, email campaigns). The agent pre-generates redline suggestions in the CEO's voice so the CEO only tweaks and approves — not writes reviews from scratch.

**Company:** [PLACEHOLDER — Appian IT services company name]

---

## How It Works

1. JIRA tickets with `status = "CEO Review"` populate the dashboard queue
2. Each ticket links to a Word doc on SharePoint
3. The agent fetches the doc, reads `review-style.md`, and generates redline suggestions (as Word comments)
4. CEO sees a side-by-side view (original left, suggested right) in the dashboard
5. CEO edits suggestions if needed, hits Approve
6. Redlined `.docx` (with comments) is written back to SharePoint
7. JIRA ticket is reassigned to the original assignee and status reverts to pre-"CEO Review"
8. `style_learner.py` diffs agent suggestions vs CEO's final edits and updates `review-style.md` automatically

---

## Stack

- **Backend:** Python + FastAPI (`backend/`)
- **Frontend:** React + TypeScript (`frontend/`)
- **Word docs:** `python-docx`
- **Claude API:** `anthropic` Python SDK — default model `claude-sonnet-4-6`, upgrade path to `claude-opus-4-8` via `CLAUDE_MODEL` env var
- **JIRA:** Atlassian REST API (`jira` Python library)
- **SharePoint:** Microsoft Graph API (`msgraph-sdk-python`)

---

## Project Structure

```
review-agent/
├── CLAUDE.md                    # This file
├── review-style.md              # CEO style memory — git versioned
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── routers/
│   │   ├── queue.py             # GET /queue
│   │   ├── review.py            # GET /review/{ticket_id}
│   │   └── approve.py           # POST /approve
│   ├── services/
│   │   ├── jira.py              # JIRA REST client
│   │   ├── sharepoint.py        # Microsoft Graph client
│   │   ├── docx_service.py      # python-docx read/write comments
│   │   ├── review_agent.py      # Claude API review generation
│   │   └── style_learner.py     # Post-approval style learning
│   └── .env                     # Credentials (never commit)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Queue.tsx        # Ticket list panel
│   │   │   ├── ReviewPane.tsx   # Side-by-side original/suggested
│   │   │   └── EditBox.tsx      # CEO inline edit before approve
│   │   └── api.ts               # FastAPI fetch wrappers
│   └── package.json
└── .agents/
    └── skills/
        └── grill-me/            # Design interview skill
```

---

## Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
# Runs on http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev
# Runs on http://localhost:3000
```

---

## Environment Variables (`backend/.env`)

```
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-sonnet-4-6

JIRA_URL=https://[PLACEHOLDER].atlassian.net
JIRA_EMAIL=[PLACEHOLDER — CEO's JIRA email]
JIRA_API_TOKEN=

AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
SHAREPOINT_SITE_URL=https://[PLACEHOLDER].sharepoint.com/sites/[PLACEHOLDER]
```

---

## JIRA Queue Logic

- Filter: `status = "CEO Review"`
- On approve: revert ticket status to the status it was in before "CEO Review", reassign to original assignee (captured from ticket history)

---

## Style Memory (`review-style.md`)

- Lives at repo root, git versioned
- Read by `review_agent.py` on every review call
- Updated automatically by `style_learner.py` after each CEO approval (diffs agent suggestion vs CEO's final version)
- Review git diff of this file to validate what the agent learned — commit to keep, revert to discard

---

## Training Data

- 20+ CEO-authored final `.docx` files stored on SharePoint
- Ingested once via `backend/services/sharepoint.py` to seed `review-style.md`
- Some docs may contain residual Word comments — extract these as additional style signal
- Run `python backend/scripts/ingest_samples.py` to re-run style extraction

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Output format | Word comments (not tracked changes) | Cleaner, easier to read in browser and Word |
| Trigger | Manual — CEO opens dashboard | No surprise runs |
| Pre-generation | Eager — runs when ticket enters queue | Zero wait time for CEO |
| Style learning | Auto-update `review-style.md` after each approval | No CEO time spent on learning loop |
| Model default | `claude-sonnet-4-6` | Fast + cost-efficient; Opus upgrade via env var |
| Auth | Azure AD OAuth 2.0 (covers SharePoint + Graph) | Single app registration for Microsoft stack |

---

## Build Order

1. Microsoft Graph auth + SharePoint file fetch/write
2. JIRA REST client — queue query + ticket history
3. `docx_service.py` — extract text, write comments
4. Ingest 20+ CEO sample docs → seed `review-style.md`
5. `review_agent.py` — generate redline suggestions from doc + style memory
6. FastAPI routes: `/queue`, `/review/{ticket_id}`, `/approve`
7. React dashboard — queue panel, side-by-side review, edit box, approve button
8. `style_learner.py` — post-approval learning loop
