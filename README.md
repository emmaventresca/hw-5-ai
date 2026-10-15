# Campus Customs — Multi-Agent Operations Desk

A five-agent team that runs a small Yale apparel shop: it reads the open tickets,
routes each one to the right specialist, checks the real database before it says
anything, and stops at a human for every dollar that leaves the account.

Three pieces: an **MCP server** over the shop database, a **FastAPI backend**
that orchestrates the agents, and a **React board** where you watch them work
and approve payments.

---

## The agents

| Agent | Owns |
| --- | --- |
| **Boss** | Reads every ticket, decides who works it, makes the final call |
| **Inventory** | Stock counts, vendors, lead times, restock feasibility |
| **Accounting** | Cash, invoices, margins, prepares payments for approval |
| **Facilities** | Leases, rent, the shop space |
| **Customer Service** | Drafts what the customer reads — held internally, never sent |

Agent instructions live in `backend/prompts/`, one file per agent.

---

## Setup

Python work happens in a project-local virtualenv.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Secrets go in a local, git-ignored `.env`:

```bash
cp .env.example .env
```

Then install the frontend:

```bash
npm --prefix frontend install
```

---

## Running it

Start the three pieces in this order. Each wants its own terminal.

### 1. Reset the working database

Do this **before any full three-ticket run**. `data/campus_customs.db` is the
pristine original and is never written to; `data/campus_customs_new.db` is the
working copy the agents actually modify.

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

Once the backend is up you can do the same thing from the board's **Reset board**
button, or with `curl -X POST localhost:8000/reset-db`. Either way you are back
to a **$3,400.00** checking balance with all three tickets open.

### 2. MCP server

```bash
python -m mcp_server.server
```

Reads `data/campus_customs_new.db`. Registered for this project in `.mcp.json`.

### 3. FastAPI backend

```bash
uvicorn backend.main:app --reload --port 8000
```

Check it with `curl localhost:8000/health`.

### 4. React board

```bash
npm --prefix frontend run dev
```

Open **http://localhost:5173**. The backend already allows that origin via CORS.

---

## A full three-ticket run

1. Reset the database (step 1 above), so you start from **$3,400.00**.
2. Click ticket **101**, press **Run agent team**, then **Approve payment**
   ($840.00 to Bulldog Print Co for overdue invoice 501).
3. Click ticket **102**, run it, approve ($2,400.00 rent to Elm City Properties).
4. Click ticket **103** and run it. No payment — it resolves on its own.
5. Checking now reads **$160.00** and all three tickets show resolved.

Order matters for what you see, not for the total. Paying invoice 501 on ticket
101 clears Bulldog Print Co, so when ticket 103 asks the same vendor for 12
hoodies, Inventory reports the lead time actually holds. Run 103 first and the
same agent correctly refuses to promise a date.

```
$3,400.00  starting balance
−  840.00  ticket 101 — vendor payment, invoice 501
− 2,400.00  ticket 102 — rent payment, lease 1
−     0.00  ticket 103 — quote only, no cash
─────────
$  160.00  ending balance
```

---

## API routes

All served from `http://localhost:8000`.

| Route | Does |
| --- | --- |
| `GET /health` | Service health |
| `GET /tickets` | The three tickets and whether each is open or resolved |
| `POST /run-ticket/{id}` | Runs the agent team on one ticket; returns the events and any prepared payment |
| `GET /agent-events` | The full audit trail |
| `GET /cash-balance` | Current checking balance |
| `POST /approve-payment` | **The only route that moves cash.** Agents prepare; a human releases |
| `POST /reset-db` | Restores the working copy from the pristine database |

---

## Safety rules the team follows

- **Human approval for every payment.** Agents prepare, they never release.
  `POST /approve-payment` is the only path that touches `cash_accounts`.
- **Never go negative.** A payment larger than the balance is refused with a 400
  and the refusal is written to the audit trail.
- **Pay, then update.** An approved vendor payment marks its invoice `paid`.
- **No outbound contact.** Customer Service drafts stay on the board. Nothing is
  emailed to a customer and no vendor is called.
- **Nothing invented.** Every figure an agent states is read from the database.
  If the backend is down the board says so rather than showing sample data.
- **Secrets stay local.** `.env` is git-ignored; only `.env.example` is committed.

---

## Where things are

```
AI_prompts.md              Every prompt used to build this, in order
requirements.txt           Python dependencies
.env.example               Template for local secrets
.mcp.json                  MCP server registration
data/
  campus_customs.db        Pristine original — never written to
  campus_customs_new.db    Working copy the agents modify
mcp_server/
  server.py                Nine tools over the shop database
  README.md
backend/
  main.py                  FastAPI app, agent orchestration, seven routes
  models.py
  prompts/                 One instruction file per agent
frontend/                  React + Vite + TypeScript board
output/
  harness.md               Tables, tools, agents, routes, dashboard, safety rules
  mcp_smoke.json           Evidence that each MCP tool returns real values
  desk_tickets.html        Expected plan vs. actual run, cash ledger, reflection
  design.md                Why the board looks the way it does
  resolved_tickets.json    Final status, agent contributions, approvals
  resolved_board.html      Screenshots of the board for each resolved ticket
  audit_trail.json         Append-only log of every agent action
  github_url.txt           Repository URL
```
