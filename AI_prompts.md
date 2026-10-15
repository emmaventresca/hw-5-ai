# Campus Customs Multi-Agent Operations System
## AI Prompts & Problem Log

---

## Question One: System Architecture & Initial Setup

**Problem Number & Title:** Q1 — Campus Customs Multi-Agent Architecture Overview

**User Prompt (Own Words):**
> "We're going to build a campus customs multi-agent operations thing to build an agent team that runs the shop. Open tickets land on a board with customers orders, returns, unpaid bills, discount requests, whatever else the shop has to handle. We're gonna build this in three pieces - MCP server, a FastAPI backend with a multi-agent team and React dashboard so a human can watch the agents at work and approve requests."

**Agent Team Defined:**
- **Boss** — reads each ticket, decides who should work on it, makes final calls
- **Inventory** — checks stock by SKU and size, spots shortfalls, figures out which vendor can restock
- **Accounting** — watches cash and invoices, checks margins, prepares payment or purchase orders for human approval
- **Facilities** — handles shop space side: leases, rent, etc.
- **Customer Service** — drafts messages for customers

**Key Architecture Constraints:**
- Full agent connectivity — any agent can delegate tasks to any other agent for help
- Human approval required for all payments (points deducted if not done)
- Multi-agent team backed by SQLite database
- React dashboard allows humans to watch agents work and approve requests
- Three-component deployment: MCP server, FastAPI backend, React frontend

**File Structure Defined:**
```
AI_prompts.md
requirements.txt
.env.example
.gitignore
.mcp.json
README.md
data/        campus_customs.db, campus_customs_new.db
mcp_server/  server.py, README.md
frontend/
backend/     main.py, models.py
             prompts/  boss.md, inventory.md, accounting.md,
                       facilities.md, customer_service.md
output/      harness.md, mcp_smoke.json, desk_tickets.html, design.md,
             resolved_tickets.json, resolved_board.html,
             audit_trail.json, github_url.txt
```

**Follow-Up Clarifications:**
- Database strategy: `campus_customs.db` = pristine original (untouched), `campus_customs_new.db` = working copy for agent modifications
- Reset procedure: copy original DB to working copy when starting a fresh run
- Deployment order: start MCP server → start FastAPI backend → start React board
- Grader access: push to public GitHub; URL goes in `output/github_url.txt`
- No `.env` in git (use `.env.example` template); both `.db` files DO get committed to `data/`

**Database Schema (from original file):**
Tables: `desk`, `tickets`, `inventory`, `pricing`, `vendors`, `leases`, `cash_accounts`, `payments`, `invoices`

**Shop Operational Rules:**
- `desk.date_today` = shop's current date (use to determine overdue tickets)
- Vendor lead times from `vendors` table
- Vendors won't ship new product while they have open unpaid invoices
- If payment made, update relevant table
- No negative cash balance (pay tool refuses if insufficient funds)
- Cash only flows out (no revenue in — test scenario)
- Before full run: reset DB to original values
- Do NOT email customers or call vendors — all drafts stay internal on the board

**Model Configuration:**
- Use `gpt-luna-6` for all agent prompts
- Portkey API key in local `.env` file (never in chat or code)

**Status:** ✓ File structure defined, rules captured, ready to begin implementation

---

---

## Question Two: Study the Campus Customs Database

**Problem Number & Title:** Q2 — Database Schema & Open Ticket Linkage

**User Prompt (Own Words):**
> "Study the campus customs database. Open data/campus_customs.db and look through every table and fields. Copy the original file to data/campus_customs_new.db. Then study the three open tickets so we see how they link to the other tables. Start output/harness.md: for each table list the fields in one short line on why that table matters for the agent."

**Database Copy:** ✓ `campus_customs.db` copied to `campus_customs_new.db` (working copy for agent updates)

**Tables Identified:** 9 tables with 41 total fields across `desk`, `tickets`, `inventory`, `pricing`, `vendors`, `leases`, `cash_accounts`, `payments`, `invoices`

**Three Open Tickets:**
- **Ticket 101:** Customer order (Tauhid Zaman) for Bulldog tee, size S — current stock is 0 (blocked by overdue Invoice 501)
- **Ticket 102:** Rent notice (Elm City Properties) for Chapel Street shop — $2400 due 2026-09-02 (2 days away)
- **Ticket 103:** Bulk discount request (Yale AI Club) for 20 Bulldog hoodies, size M — current stock 8 (short 12)

**Status:** ✓ Database catalogued in `output/harness.md` with table purpose and agent use cases

---

## Question Three: Build the MCP Server

**Problem Number & Title:** Q3 — MCP Server with Three Core Tools

**User Prompt (Own Words):**
> "Build the MCP server in mcp_server/ using fast-mcp. It talks to data/campus_customs_new.db. Write only three tools that we know we'll need for the tickets. Keep names clear, don't invent data, only use the database. Then list each tool in harness.md with which table it reads, which ticket it helps unlock (101, 102, or 103), and why it's the right one for that ticket—specific and descriptive, not vague."

**Tool 1: `get_inventory_stock(sku, size)`**
- Tables: inventory
- Tickets: 101, 103
- Detail: Boss queries CC-TEE-WHITE S for ticket 101 (returns 0, spots shortfall immediately). Inventory checks CC-HOOD-NAVY M for ticket 103 (returns 8, calculates 12-unit gap for restock).

**Tool 2: `get_open_invoices_for_vendor(vendor_id)`**
- Tables: invoices
- Tickets: 101
- Detail: Accounting queries vendor_id=1 for ticket 101 and discovers Invoice 501 ($840, overdue 2026-08-28) must be paid before Bulldog Print Co ships new stock; this gates the entire fulfillment flow.

**Tool 3: `get_lease_details(lease_id)`**
- Tables: leases
- Tickets: 102
- Detail: Facilities queries lease_id=1 for ticket 102, retrieves Chapel Street rent ($2400, due 2026-09-02), and passes urgency + amount to Accounting for cash check and payment approval.

**Files Created:**
- ✓ `mcp_server/server.py` — 3 tools using fast-mcp, queries campus_customs_new.db
- ✓ `mcp_server/README.md` — explains server purpose, database file, and tool list
- ✓ `output/harness.md` — extended with table catalog + tool documentation for each ticket

**Critical Constraints Met:**
- No hallucinated data (only actual DB values used)
- Tools are named clearly and tied to specific tickets
- Each tool unblocks real bottlenecks in the ticket resolution flow

**Status:** ✓ MCP server built with three production-ready tools; ready to connect and test later

---

---

## Question Four: Connect MCP Server & Test All Tools

**Problem Number & Title:** Q4 — Add MCP Server to Claude Code and Smoke Test Each Tool

**User Prompt (Own Words):**
> "Add the MCP server to this Claude Code project. Save the JSON connection in .mcp.json at the project root—that's how the VibeCoder saves the local MCP server list. Now test each of the three MCP tools. Don't skip anything, don't hallucinate. Save the evidence in output/mcp_smoke.json with three things for each test: the prompt we asked, the tool name, and the tool output—which must match the actual values in campus_customs_new.db."

**Status:** In progress — building .mcp.json and testing tools now...

---

## Question Five: Build Agent Team & Expand MCP Tools

**Problem Number & Title:** Q5 — Multi-Agent Team with Pydantic AI and Extended MCP Tools

**User Prompt (Own Words):**
> "Build the agentic team for Campus Customs using Pydantic AI. Five agents: Boss, Inventory, Accounting, Facilities, Customer Service. Put prompts in backend/prompts/ (one file per agent), data tables in backend/models.py, agent files under backend/. Use gpt-luna-6 only. Write full prompts for each agent covering their work scope and shop rules. Add any tools the agents need to the MCP server. Wire agents to append to output/audit_trail.json as they run—keep appending, don't wipe. Update harness.md with agent-to-tool mappings and add a safety section: no sensitive data, reasonable token spend limit ($1-2 per run), keep identity private. Update mcp_server/README.md with guardrails."

**Agent Roles & Responsibilities (from user's own words):**

1. **Boss Agent**
   - Read all open tickets
   - Delegate tasks to appropriate agents
   - Make final calls on decisions
   - Heuristically choose best option when multiple routes are possible

2. **Inventory Agent**
   - Check stock by SKU and size (what we have, in/out flow)
   - Spot shortfalls (identify when we need more)
   - Determine which vendor can restock fastest, cheapest, best lead time

3. **Accounting Agent**
   - Watch cash balances and invoices
   - Check margins on sales and restocks
   - Prepare payments and purchase orders for human approval
   - Interact with human for double-checking numbers and options
   - Note all transactions in and out

4. **Facilities Agent**
   - Manage leases and rent obligations
   - Review important documents
   - Ensure all bills are paid on time

5. **Customer Service Agent**
   - Draft replies to customer complaints, messages, questions
   - Keep responses internal on the board (no direct contact)

**Shop Rules:** (from Q1 setup)
- `desk.date_today` determines overdue items
- Vendor lead times from `vendors` table
- Vendors won't ship while unpaid invoices open
- ALL payments require human approval
- No negative cash balance
- Cash only flows out (test scenario)
- Before full run: reset DB

**MCP Tools:** Extend beyond Q3's three tools; add what agents need for ticket resolution

**Audit Trail:** Append to `output/audit_trail.json` each agent loop step (no wiping between runs)

**Safety Guardrails:**
- Token spend limit: $1-2 per run (adjust if needed)
- No sensitive data: biometrics, IDs, credit cards, license numbers
- Keep identity private
- No keys or important financial info in logs

**Status:** Ready to build after Q4 testing complete...

---

**Status:** ✓ Q4 Complete — MCP server tested, all three tools verified against database

---

**Agent Prompts Completed:**
- ✓ boss.md — Ticket triage, delegation, final approvals
- ✓ inventory.md — Stock checks, shortfalls, vendor selection
- ✓ accounting.md — Cash management, payment approvals, transaction logging
- ✓ facilities.md — Lease tracking, rent obligations
- ✓ customer_service.md — Customer response drafts, internal communication

**Data Models:**
- ✓ backend/models.py — 8 dataclasses (Ticket, InventoryItem, Pricing, Vendor, Lease, CashAccount, Invoice, Payment, Desk, AuditEvent) + AGENTS config dict

**MCP Tools Extended (9 total):**
- ✓ get_inventory_stock (Tickets 101, 103)
- ✓ get_open_invoices_for_vendor (Ticket 101)
- ✓ get_lease_details (Ticket 102)
- ✓ get_tickets (Boss routing)
- ✓ get_vendors (Inventory vendor selection)
- ✓ get_cash_balance (Accounting solvency checks)
- ✓ get_all_leases (Facilities overview)
- ✓ get_pricing (Margin validation, customer pricing)
- ✓ log_payment (Record human-approved payments to DB)

**Safety & Compliance:**
- ✓ Token limit: $1–$2 per ticket (gpt-luna-6 only)
- ✓ No biometric/ID/financial data in logs
- ✓ All payments require human approval
- ✓ No vendor/customer direct contact
- ✓ Audit trail append-only to output/audit_trail.json
- ✓ Database writes restricted to log_payment()

**Documentation:**
- ✓ output/harness.md — Database schema, ticket linkage, agent-tool mapping, safety guardrails
- ✓ mcp_server/README.md — All 9 tools documented with examples and guardrails
- ✓ backend/prompts/ — 5 agent prompt files with full scope and delegation patterns
- ✓ output/audit_trail.json — Template ready for event logging

**Status:** ✓ Q5 Complete — Full agent team structure ready for orchestration

---

---

## Prompt Enhancements (Q5 Follow-up)

**Problem Number & Title:** Q5 Follow-up — Comprehensive Agent Prompts with User-Supplied Details

**Status:** ✓ All Five Prompts Enhanced

### Boss Agent — Expanded Sections
- ✓ Ticket Categorization & Routing Strategy (inventory-first for orders, facilities-first for rent, accounting-first for discounts)
- ✓ Core Routing Rules with real examples (Tickets 101, 102, 103)
- ✓ Handling Ambiguous Cases (stock/vendor → Inventory, payment/cash → Accounting, complaints → Customer Service)
- ✓ Verification Checklist Before Delegating (payment-adjacent, vendor-touching, customer communication)
- ✓ Workload Monitoring & Prioritization (track agents, prioritize overdue items, escalate to human when needed)
- ✓ Escalation Trigger Examples (insufficient cash, vendor gates, policy overrides)

### Inventory Agent — Expanded Sections
- ✓ Vendor Selection Criteria (3 vendors: Bulldog 5 days, Elm City 3 days, QuickShip 1 day; cost vs. deadline trade-offs; SKU-specialty matching)
- ✓ Stock Thresholds & Shortfall Detection (0 qty = URGENT, gap tracking, reorder thresholds)
- ✓ Location & Physical Fulfillment (verify SKU location, fulfillment planning)
- ✓ Lead Time & Deadline Coordination (order date + lead days = delivery; escalate to Customer Service if deadline misses)

### Accounting Agent — Expanded Sections
- ✓ Cash Flow Forecasting (track invoices, orders, revenue by period; forecast scenarios when multiple payments due)
- ✓ Margin Analysis & Pricing Validation (cost/price/margin calculations; flagging rules: <20% flag, 20-50% acceptable, >50% healthy)
- ✓ Approval Memo Format (consistent template for human authorization with all required fields)
- ✓ Payment Prioritization (rent > vendor gates > discretionary; cash-out-only scenario)

### Facilities Agent — Expanded Sections
- ✓ Lease Portfolio Management System (track all properties, due dates, renewal dates, special terms)
- ✓ Landlord Relationship & Contact Protocol (internal-only communication, no direct contact, track negotiation history)
- ✓ Payment Timing & Grace Period Management (deadline tracking, grace period documentation, consequences of missing rent)
- ✓ Multi-Space Coordination (track multiple leases, identify payment clusters, alert Accounting on cash impact)

### Customer Service Agent — Expanded Sections
- ✓ Brand Voice & Response Tone (friendly + professional + honest; solution-focused; good vs. bad examples)
- ✓ Complaint Type Handling with Metrics (5 categories: stock inquiry, price complaint, late/damaged, returns/refunds, bulk orders; specific response framework for each)
- ✓ Verification & Non-Unilateral Decision-Making (pre-draft checklist; escalation rules for Accounting and Boss)
- ✓ Response Draft Format (consistent template with AGENT NOTES; real example for Ticket 103 bulk order)

**Key Improvements:**
- Every prompt now includes specific MCP tool calls
- Real ticket examples (101, 102, 103) woven throughout
- Clear escalation pathways (when to route to which agent)
- Detailed decision trees for complex scenarios
- Non-unilateral action guardrails (no auto-approvals, no direct contact)
- Audit trail expectations (what gets logged and why)

**Status:** ✓ Q5 Prompts Complete — Ready for orchestration/agent loop implementation

---

## Question Six: Plan the Three Tickets Before Building

**Problem Number & Title:** Q6 — Expected Resolution Paths

**User Prompt (Own Words):**
> "Before we work on the back end, we want to write down what we think is going to happen with the team looking at each open ticket. Put that in `output/desk_tickets.html` — a tab per ticket, plus empty cache and reflection tabs. For each ticket's expected, we fill in after we run the agents, then compare plan to what actually happens. Don't want every specialist on every ticket — streamlined process just for efficiency. For each ticket show: 1) who boss calls first and why, 2) all agent delegations, 3) what MCP tools we expect this run to use."

**Expected paths recorded (user's own words, filler removed):**
- **101** — Boss calls Inventory first (out of stock item, we have zero). Then Accounting for the overdue invoice, then Customer Service to draft the reply. Restock from Bulldog Print Co, five-day lead. "Everyone but facilities."
- **102** — Boss calls Facilities first (they are in charge of the shop space, including leases and rent), then Accounting for the cash outflow, with human approval kept in the loop.
- **103** — Boss calls Inventory first for a feasibility check (12-hoodie gap), then Accounting for margin, then Customer Service — margin confirmed healthy before any discount number goes out.

**Status:** ✓ Plans written before any orchestration existed, so the comparison is honest.

---

## Question Seven: Backend Routes

**Problem Number & Title:** Q7 — FastAPI Backend

**User Prompt (Own Words):**
> "For question seven, this is called backend routes. We want the React frontend dashboard to have a backend that it can call. In `backend/main.py` use FastAPI and add routes. First, return the three tickets and whether each is open or resolved. Then take a ticket ID and run the agent team on the ticket. Then return agent events. Approve a payment or purchase after a human clicks approve — that means agents only prepare the pay, and this route is actually what changes cash. Return the current balance from `cash_accounts`. Reset the database to the original values every time we want a fresh run. And in `output/harness.md` list each route in one line, what the URL is and what it does. Be succinct, be accurate, double check your work."

**Routes built:** `/health`, `/tickets`, `/run-ticket/{id}`, `/agent-events`, `/cash-balance`, `/approve-payment`, `/reset-db`.

**Key design decision:** `POST /approve-payment` is the only route that touches `cash_accounts`. Agents prepare a `pending_approval`; nothing moves until a human releases it. A payment larger than the balance is refused with a 400 and the refusal is written to the audit trail.

**Status:** ✓ All seven routes implemented and documented in `output/harness.md`.

---

## Question Eight: React Agent Dashboard

**Problem Number & Title:** Q8 — The Board

**User Prompt (Own Words):**
> "We create the React front end — this is the agent dashboard. Build it in `frontend/` with React, Vite and TypeScript. Our board should list all three tickets, let you pick a ticket and start the agent team on it, show each agent what they're saying and doing while the ticket runs, mark a ticket resolved when it finishes a run, show a short summary of what each agent did on the ticket, let a human approve a pay or purchase when asked, and show the checking balance which should drop after an approved pay. Agents on the left side, a panel in the middle having the summary and changes made, and on the right side seeing what activity is currently running. The front end talks to the back end at localhost:8000, and allow the Vite page origin, which is usually localhost:5173."

**Follow-up direction:** The first build was rejected as looking AI-generated. The user asked for a sleeker, more professional dashboard (referencing joinpogo.com), a cream and navy palette, brighter ticket text, softer edges, animal avatars per agent for personality, a rotating line in the header, a "show email draft" control for Customer Service, and a way to open Accounting's math.

**Status:** ✓ Built and verified live against the backend at desktop and mobile widths. Visual rationale recorded in `output/design.md`.

---

## Question Nine: Full Three-Ticket Run

**Problem Number & Title:** Q9 — Run It For Real

**User Prompt (Own Words):**
> "Before we test the agents on a full run, reset the working database `data/campus_customs_new.db` so we have a clean run to start. Take note of the starting checking balance, then run all three tickets on the board — 101, 102 and 103 — until we've resolved each. Then open `output/desk_tickets.html` from problem six and on each of the ticket tabs fill the actual section from this run, meaning which agents worked, what they delegated, and which tools they used. Keep the expected section so we can compare the two — don't overwrite expected. On the cache tab, itemize the money: the starting checking balance after a reset, then for each individual ticket how the cash changed when the ticket was resolved and why, and the ending checking balance. This has to match `cash_accounts` in the working database. We're going to lose a ton of points if we have wrong cash math. Also save `output/resolved_tickets.json` and `output/resolved_board.html` with a screenshot of the React board for each resolved ticket, append the real runs to `output/audit_trail.json` without overwriting, and finish `output/harness.md` so it covers the tables, MCP tools, the five agents, API routes, the dashboard and the safety rules."

**Verified result:** $3,400.00 → $160.00 across all three tickets, two human approvals, reconciled three independent ways against `cash_accounts` and `payments`.

**Status:** ✓ Complete. Evidence in `desk_tickets.html`, `resolved_tickets.json`, `resolved_board.html`, `audit_trail.json`, `harness.md`.

---

## Question Ten: Reflection

**Problem Number & Title:** Q10 — Evaluating the Agents

**User Prompt (Own Words):**
> "Fill the reflection tab in `output/desk_tickets.html`, in my own vibe, detailed and thorough. The questions are: how would you evaluate the performance of the agents on each ticket and why; for each ticket how did the actual compare to the expected plan; what would have been simpler as one agent with tools and why; describe three new problems Campus Customs might face that this agent team could solve with the tools we built, naming the specific tools; and describe three new problems it could not solve, explaining the tools and agents you would need."

**Status:** ✓ Written as a developed essay in the Reflection tab, in the user's own voice and arguments.

---

## Question Eleven: Push to GitHub

**Problem Number & Title:** Q11 — Public Repository

**User Prompt (Own Words):**
> "Problem 11 is pushing to GitHub, and it has to be a public repository so that the graders can clone it. We submit the repo URL to Canvas and put it in `output/github_url.txt`. We don't want to push the real `.env` to the GitHub repo, but we do want to include both of the database files under `data/` — the original and the working copy — so that the graders can run the app easily. The README should explain copying the original DB to the working copy when you need a clean run, starting the MCP server, the FastAPI backend and the React board, and resetting the DB before a full three-ticket run. Try that yourself while you're checking through everything — this should work on our system as well as all the graders'."

**Pre-push verification performed:**
- `.env` confirmed excluded; only `.env.example` with a placeholder is committed
- Both `data/*.db` files committed so the app runs on clone
- Repository scanned for key patterns before the first commit
- `frontend` production build run clean
- MCP server, FastAPI backend and React board each started from the documented commands
- Full three-ticket run re-executed through the live API and reconciled against the database

**Status:** ✓ Repository prepared and verified.

---
