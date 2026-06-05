# AI Refund Agent

A full-stack AI system that handles customer refund requests end-to-end — from natural language conversation to a logged, auditable decision. Customers chat with an AI assistant that collects the necessary details; a deterministic policy engine then evaluates the request against a configurable ruleset and either approves, denies, or escalates it to a human. The LLM explains decisions in plain language; it never makes them. That separation keeps the system predictable, auditable, and safe to deploy without a human in the loop for routine cases.

---

## Try It Live

**Chat:** [https://ai-refund-agent-assessment.vercel.app](https://ai-refund-agent-assessment.vercel.app)

Use one of the seeded test accounts below. Just tell the agent your email and order ID in plain language — no special format needed.

| Scenario | Email | Order | Expected outcome |
|---|---|---|---|
| Standard refund | `sarah.chen@outlook.com` | ORD002 | ✅ Approved — running shoes, within return window |
| Large order | `james.wilson@gmail.com` | ORD007 | ⚠️ Escalated — laptop over $500 threshold |
| Changed mind | `emily.johnson@gmail.com` | ORD004 | ✅ Approved — within return window |
| Defective item | `michael.torres@yahoo.com` | ORD003 | ✅ Approved — mention it arrived damaged |

**Example message to get started:**

> *"Hi, I'm sarah.chen@outlook.com. I'd like a refund for order ORD002 — the running shoes don't fit."*

---

## Architecture Overview

The system has three main components:

- **Synthetic data layer** — 15 seeded customers and 14 orders covering every policy branch, so the agent works out of the box without real customer data.
- **Backend agent** — A FastAPI server hosting a LangGraph state machine. Each conversation flows through fixed nodes (safety check → intent extraction → identity resolution → policy evaluation → response composition), with deterministic routing between them.
- **Frontend UI** — A Next.js app with two surfaces: a customer chat interface and an internal admin dashboard that exposes the full agent trace for every run.

```
Customer Chat
     │
     ▼
 FastAPI /chat
     │
     ▼
LangGraph Agent
 ├─ safety_check        (injection detection)
 ├─ intent_extraction   (LLM parses request)
 ├─ identity_resolution (DB lookup by email/ID)
 ├─ context_assembly    (order + item details)
 ├─ policy_evaluation   (deterministic engine)
 └─ response_composition (LLM writes reply)
     │
     ▼
  SQLite DB ◄──── Admin Dashboard
                  /admin (full trace view)
```

> **The LLM never decides the verdict. The policy engine does.**

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js 14, React 18, Tailwind CSS | Customer chat and admin dashboard |
| Backend | FastAPI, Python 3.11 | REST API, request handling |
| Agent | LangGraph, OpenAI SDK | Stateful multi-node conversation graph |
| Policy Engine | Custom Python + `rules.yaml` | Deterministic refund verdict logic |
| Database | SQLite / SQLAlchemy | Conversation logs, refund records, seed data |
| Container | Docker Compose | Single-command local deployment |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An OpenAI API key (or compatible provider — see `LLM_BASE_URL` below)

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd refund-agent

# 2. Copy the example environment file
cp .env.example .env

# 3. Add your OpenAI API key to .env
#    Edit .env and set OPENAI_API_KEY=sk-...

# 4. Start all services
docker-compose up

# 5. Open the app
#    Customer chat:      http://localhost:3000
#    Admin dashboard:    http://localhost:3000/admin
#    API docs (Swagger): http://localhost:8000/docs
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI (or compatible) API key |
| `MODEL_NAME` | No | `gpt-4o` | Model to use for LLM nodes |
| `LLM_BASE_URL` | No | OpenAI default | Override to point at a local model (e.g. Ollama) |
| `ADMIN_SECRET` | No | `changeme` | Secret sent in `x-admin-secret` header to access admin endpoints |
| `DATABASE_URL` | No | `sqlite:///./refund_agent.db` | SQLAlchemy database URL |

---

## Agent Loop Explained

Each `/chat` request runs the full LangGraph state machine from scratch. The graph is deterministic in structure — only the LLM-powered nodes introduce variability, and their outputs are validated before use.

1. **Safety Check** — Scans the incoming message for prompt injection patterns (role overrides, jailbreak attempts, instruction leakage). Detected injections short-circuit to a deflection response; clean messages continue.

2. **Intent Extraction** — The LLM classifies the message as a refund request or not, extracts structured fields (reason category, order reference, evidence claim), and flags any missing information that would block evaluation.

3. **Identity & Order Resolution** — Tool calls look up the customer by email or ID and fetch the referenced order and line item from the database. Nothing here comes from user input directly — all facts are DB-sourced.

4. **Policy Evaluation** — A purely deterministic Python function evaluates the assembled context against `rules.yaml`. No LLM involved. Outputs one of: `approved`, `denied`, or `escalated`, plus a list of reason codes.

5. **Response Composition** — The LLM receives the policy verdict and reason codes and writes a natural-language explanation for the customer. It cannot change the verdict — it can only explain it.

Every run is logged in full: parsed intent, tool call results, policy input and output, final response, latency, and any injection flags.

---

## Refund Policy

The policy engine evaluates four primary rules, all configurable in `backend/app/policy/rules.yaml` without touching application code:

- **Final sale items** are never refundable, regardless of condition, timing, or stated reason.
- **High-value orders (> $500)** are escalated to a human reviewer rather than auto-decided, regardless of other factors.
- **Outside the return window** (default: 30 days from delivery) results in an automatic denial. Defective items get an extended window of 60 days.
- **Damaged or defective items** are conditionally approved when evidence is provided; escalated to human review when no evidence is present.

To tighten or relax any threshold, edit `rules.yaml` and restart the backend — no code change required.

---

## Safety & Prompt Injection

Three independent layers guard against adversarial input:

- **Detection layer (`safety/injection.py`)** — Pattern-matches the incoming message against a catalogue of injection techniques (role overrides, instruction injection, privilege escalation attempts). Flagged messages are deflected before any LLM call is made.
- **DB-sourced facts** — Customer name, order status, item details, and pricing are all fetched from the database and injected into the LLM context by the agent. The user cannot supply or override these facts through the chat interface.
- **Output guard (`safety/output_guard.py`)** — Validates the LLM's response before it is sent, ensuring it does not leak internal system details (policy engine internals, reason codes, prompt structure) and that the verdict token is one of the three permitted values.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Submit a customer message; returns reply, verdict, and conversation ID |
| `GET` | `/health` | Liveness check; returns model name |
| `GET` | `/admin/logs` | Paginated list of agent run logs (`?page=1&page_size=20`) |
| `GET` | `/admin/logs/{log_id}` | Full trace for a single agent run |
| `GET` | `/admin/refund-requests` | Paginated refund requests (`?decision=approved\|denied\|escalated`) |
| `GET` | `/admin/refund-requests/{id}` | Detail view with customer and order context |
| `GET` | `/admin/escalations` | All open escalations in one list |
| `GET` | `/admin/customers` | Paginated customer list with order counts |

All `/admin/*` endpoints require the `x-admin-secret` header. Full interactive documentation is available at **http://localhost:8000/docs**.

---

## Admin Dashboard

The dashboard at `http://localhost:3000/admin` gives operators full visibility into every agent run without touching the database directly.

- **Conversations tab** — Each row is one agent invocation. Clicking it opens a side panel with the complete run trace: the raw customer message, parsed intent JSON, every tool call and its result, the exact policy input, the verdict with reason codes, the final response sent to the customer, and any injection flags detected.
- **Escalations tab** — A prioritised queue of all refund requests that require human review, with the reason for escalation shown on each card. Refreshes silently every 30 seconds.

---

## Seed Data

On first startup the database is populated with 15 synthetic customers and 14 orders, deliberately engineered to exercise every branch of the policy engine. The fixture set includes: a straightforward approval within the return window; a final-sale denial; an out-of-window denial; a high-value order escalation (> $500); a defective item with photo evidence attached (approved); and a defective item reported without evidence (escalated). This means every policy path can be tested interactively without constructing edge-case data by hand.

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

| File | Covers |
|---|---|
| `test_policy_engine.py` | All deterministic verdict rules — final sale, return window, escalation threshold, defective with/without evidence |
| `test_agent_flows.py` | End-to-end graph invocation for each policy branch |
| `test_injection.py` | Injection pattern detection and deflection routing |
| `test_tools.py` | Database tool calls — identity resolution, order lookup |

---

## Project Structure

```
refund-agent/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── agent/          # LangGraph graph, nodes, tools, prompts
│   │   ├── policy/         # Deterministic engine + rules.yaml
│   │   ├── safety/         # Injection detection + output guard
│   │   └── db/             # SQLAlchemy models, session, seed runner
│   ├── fixtures/           # Seed JSON (customers, orders, products)
│   └── tests/
└── frontend/
    ├── Dockerfile
    └── src/app/
        ├── page.tsx         # Customer chat interface
        └── admin/           # Admin dashboard + components
```

---

## Limitations & Next Steps

This is a demonstration project. Known gaps before production use:

- **Auth is mocked** — customers identify themselves by typing their email or customer ID in the chat. There is no session token, login flow, or identity verification.
- **No real payment processing** — the agent approves refunds in the database only. Connecting to Stripe, Shopify, or a payment gateway is a clear next step but not implemented.
- **No escalation notifications** — escalated requests are queued in the admin dashboard but no Slack message, email, or webhook is sent to alert a human reviewer.
- **SQLite only** — fine for development and demos. The `DATABASE_URL` env var accepts any SQLAlchemy-compatible URL, so a Postgres migration is straightforward but untested.
- **Single tenant, single policy** — the rule set is global. Supporting multiple merchants or configurable per-customer policies would require a schema change and multi-tenancy logic.
