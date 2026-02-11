# Lead Ops Automation

**Project:** Sales Lead Qualification Automation  
**Project name:** lead-ops-automation

Production-grade automation for inbound lead qualification, routing, and logging. Built for **retry safety**, **idempotency**, and **full observability**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INBOUND LEADS                                      │
│  (Forms, Website, WhatsApp, Ads)                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              n8n                                             │
│  • Webhook intake                                                            │
│  • Retries (3x, 2s backoff)                                                  │
│  • Conditional branching (qualified vs cold)                                 │
│  • Slack / Google Sheets / Error handling                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Python FastAPI (api:8000)                             │
│  POST /enrich-lead                                                            │
│  • Idempotency: sha256(email + phone)                                         │
│  • LLM: classification + structured extraction                               │
│  • Strict Pydantic schema                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PostgreSQL                                         │
│  • runs: full audit trail (payload, result, status, error)                   │
│  • idempotency_keys: deduplication                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- OpenAI API key

### Setup

```bash
# 1. From backend directory
cd backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env file
cp .env.example .env
# Edit .env: set DATABASE_URL and OPENAI_API_KEY

# 5. Setup database
# Option A: Use SQLAlchemy auto-create (development)
# Tables will be created automatically on first run

# Option B: Run migrations manually (production)
psql -U postgres -d lead_ops -f migrations/001_init.sql

# 6. Start API server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 7. Health check
curl http://localhost:8000/health
```

---

## API

### POST /enrich-lead

**Input:** Raw JSON lead payload (unknown structure allowed)

```json
{
  "email": "jane@acme.com",
  "phone": "+1234567890",
  "message": "Looking for enterprise plan, budget $50k",
  "source": "website_form"
}
```

**Output (strict schema):**

```json
{
  "qualified": true,
  "score": 82,
  "reasons": ["High budget", "Urgent intent"],
  "lead": {
    "name": "Jane Doe",
    "email": "jane@acme.com",
    "phone": "+1234567890",
    "budget": 50000,
    "intent": "Enterprise plan",
    "urgency": "high",
    "industry": "Technology"
  }
}
```

### JSON Schema

```json
{
  "type": "object",
  "required": ["qualified", "score", "reasons", "lead"],
  "properties": {
    "qualified": { "type": "boolean" },
    "score": { "type": "integer", "minimum": 0, "maximum": 100 },
    "reasons": { "type": "array", "items": { "type": "string" } },
    "lead": {
      "type": "object",
      "properties": {
        "name": { "type": ["string", "null"] },
        "email": { "type": ["string", "null"] },
        "phone": { "type": ["string", "null"] },
        "budget": { "type": ["number", "null"] },
        "intent": { "type": ["string", "null"] },
        "urgency": { "enum": ["low", "medium", "high", null] },
        "industry": { "type": ["string", "null"] }
      }
    }
  }
}
```

---

## Failure Handling

| Scenario | Behavior |
|---------|----------|
| **Duplicate request** (same email+phone) | Returns cached result, no LLM call |
| **LLM schema mismatch** | 502, run logged as `failed`, idempotency key released for retry |
| **LLM timeout/error** | 502, run logged, key released |
| **DB unavailable** | 500, request fails |
| **409 Conflict** | Another request with same key is still processing; retry with `Retry-After: 5` |

**Retry rules:**
- Idempotency check happens **before** LLM call
- Failed runs release the idempotency key so retries can reprocess
- n8n HTTP node: 3 retries, 2s between tries

---

## Database

### runs

| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| idempotency_key | varchar(64) | Links to idempotency_keys |
| source | varchar(255) | Lead source |
| payload_json | jsonb | Raw input |
| result_json | jsonb | Enrichment result (null if failed) |
| status | varchar(20) | `success` \| `failed` |
| error | text | Error message (if failed) |
| created_at | timestamptz | Timestamp |

### idempotency_keys

| Column | Type | Description |
|--------|------|-------------|
| key | varchar(64) | sha256(email+phone), unique |
| created_at | timestamptz | Timestamp |

---

## n8n Workflow

Import `n8n/lead-qualification-workflow.json` into n8n (from this backend directory).

**Flow:**
1. Webhook receives POST
2. Calls `POST /enrich-lead` (with retries)
3. **If qualified:** Slack notification → Google Sheets row → Respond
4. **Else:** Tag as cold → Respond
5. **On error:** Respond with error status

**Setup:**
- `ENRICH_API_URL`: API base URL (e.g. `http://localhost:8000` or your deployed URL)
- `SLACK_CHANNEL`: Slack channel for qualified leads
- `GOOGLE_SHEET_ID`: Google Sheet for qualified leads
- Configure Slack and Google Sheets credentials in n8n

### n8n Screenshots Checklist

After import, capture:

- [ ] Webhook node configured
- [ ] HTTP Request node (Enrich Lead) with URL and retry settings
- [ ] IF node (Is Qualified?) condition
- [ ] Slack node (when qualified)
- [ ] Google Sheets node (when qualified)
- [ ] Error output path from HTTP Request
- [ ] Workflow settings (retry, max execution time)

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/lead_ops` |
| OPENAI_API_KEY | OpenAI API key | Required |
| OPENAI_MODEL | Model name | `gpt-4o-mini` |
| OPENAI_BASE_URL | Azure/OpenRouter base URL | Optional |
| LOG_LEVEL | Logging level | `INFO` |

---

## Non-Goals

- ❌ Full CRM
- ❌ OAuth flows
- ❌ UI inside n8n
- ❌ Magic auto-fixes

---

## Quality Bar

- **Retry-safe:** No duplicate Slack messages, Sheet rows, or DB entries
- **Deterministic:** Same input → same idempotency key → same result
- **Auditable:** Every run in `runs` table
- **Client-ready:** For ops teams
