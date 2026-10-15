# Campus Customs Multi-Agent Operations Harness

## Database Schema & Agent Use Cases

### Table Catalog

| Table | Fields | Agent Use |
|-------|--------|-----------|
| **desk** | `date_today`, `notes` | Provides shop's operational date to determine deadline urgency for overdue invoices, leases, and tickets |
| **tickets** | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | Central board: Customer orders, rent notices, discount requests link to inventory/invoices/leases; Boss routes each ticket to the right agent |
| **inventory** | `sku`, `name`, `size`, `qty`, `location` | Inventory agent checks stock by SKU+size to spot shortfalls and determine if restock orders are needed |
| **pricing** | `sku`, `unit_cost`, `list_price` | Accounting agent validates margins on sales; Inventory agent calculates restock margins; Customer Service uses for quoted prices |
| **vendors** | `id`, `name`, `specialty`, `lead_days` | Inventory agent identifies which vendor can restock; uses lead_days to predict fulfillment timeline |
| **leases** | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Facilities agent tracks rent obligations; Accounting checks cash against next_due dates to plan payments |
| **cash_accounts** | `name`, `balance`, `date` | Accounting agent checks available balance before approving payments; prevents negative balance on any payment |
| **payments** | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | Accounting agent logs all approved payments; Facilities verifies rent paid; audit trail for all cash moves |
| **invoices** | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Inventory agent checks for open invoices blocking vendor restocks; Accounting tracks payables and due dates |

---

## Open Tickets Linkage

### Ticket 101: Customer Order (Bulldog Tee)
- **Requester:** Tauhid Zaman | **Type:** customer_order | **Status:** open
- **Product:** CC-TEE-WHITE, size S, qty 1 | **Invoice:** 501
- **Current Inventory:** 0 in size S (out of stock)
- **Blocking Issue:** Invoice 501 (vendor_id=1, Bulldog Print Co, amount=$840, due_date=2026-08-28) is OVERDUE
- **Agent Route:** Boss → Inventory (check stock) → Accounting (approve payment for restock) → Inventory (order from Bulldog Print Co, lead_days=5)

### Ticket 102: Rent Notice (Chapel Street)
- **Requester:** Elm City Properties | **Type:** rent_notice | **Status:** open
- **Lease:** id=1, Chapel Street shop, $2400/month, next_due=2026-09-02
- **Today:** 2026-08-31 (rent due in 2 days)
- **Current Cash:** $3400 in checking account
- **Agent Route:** Boss → Facilities (check lease deadline) → Accounting (verify cash and approve rent payment)

### Ticket 103: Bulk Discount Request (Hoodies)
- **Requester:** Yale AI Club | **Type:** price_override | **Status:** open
- **Product:** CC-HOOD-NAVY, size M, qty 20 (requesting bulk discount)
- **Current Inventory:** 8 in size M (short 12 units)
- **Unit Cost:** $22, List Price: $58
- **Agent Route:** Boss → Inventory (check stock shortfall) → Customer Service (draft discount quote based on available + lead time restocking)

---

## MCP Tools for Ticket Resolution

### Tool 1: `get_inventory_stock`
- **Tables Read:** inventory
- **Tickets Unlocked:** 101, 103
- **Purpose:** For ticket 101, Boss queries current stock of CC-TEE-WHITE in size S (returns 0), immediately identifying the shortfall that triggers the need for Accounting approval on the overdue invoice. For ticket 103, Inventory checks if 20 units of CC-HOOD-NAVY size M exist in stock (returns 8), calculating the 12-unit gap and triggering a vendor restock inquiry.

### Tool 2: `get_open_invoices_for_vendor`
- **Tables Read:** invoices
- **Tickets Unlocked:** 101
- **Purpose:** For ticket 101, Accounting queries vendor_id=1 and discovers Invoice 501 ($840, due 2026-08-28) is overdue and must be paid before Bulldog Print Co will accept a new order; this is the critical gate that Inventory must report to Accounting.

### Tool 3: `get_lease_details`
- **Tables Read:** leases
- **Tickets Unlocked:** 102
- **Purpose:** For ticket 102, Facilities queries lease_id=1 to confirm the Chapel Street shop rent is $2400, due 2026-09-02 (2 days away), and passes this to Accounting to check if $3400 cash balance is sufficient and get human approval for the payment.

### Tool 4: `get_tickets`
- **Tables Read:** tickets
- **Tickets Unlocked:** 101, 102, 103
- **Purpose:** Boss opens every run with this. It returns each ticket's type, requester, sku/size/qty and its `lease_id` or `invoice_id`, which is what tells Boss where to route: a `rent_notice` carrying `lease_id=1` goes to Facilities, a `customer_order` carrying `invoice_id=501` means Inventory will hit a vendor gate.

### Tool 5: `get_vendors`
- **Tables Read:** vendors
- **Tickets Unlocked:** 101, 103
- **Purpose:** Inventory uses `lead_days` to decide whether a restock can land in time. Bulldog Print Co is the only `apparel reprint` vendor at 5 days, so both the tee reprint (101) and the 12-hoodie gap (103) depend on it. Elm City Gifts (3 days) and QuickShip CT (1 day) do not do apparel.

### Tool 6: `get_cash_balance`
- **Tables Read:** cash_accounts
- **Tickets Unlocked:** 101, 102
- **Purpose:** Accounting calls this before preparing any payment, so the memo it writes states the real balance and the real balance-after. It is read live, not cached: on ticket 102 it returned $2,560.00 rather than $3,400.00 because ticket 101's payment had already cleared.

### Tool 7: `get_all_leases`
- **Tables Read:** leases
- **Tickets Unlocked:** 102
- **Purpose:** Facilities checks the whole portfolio, not just the lease named on the ticket, so it can say whether another rent is about to land in the same window. Chapel Street is currently the only space, so the answer is no — but the check is what makes that claim trustworthy.

### Tool 8: `get_pricing`
- **Tables Read:** pricing
- **Tickets Unlocked:** 103 (and 101 for the drafted reply)
- **Purpose:** Accounting's margin work on ticket 103 runs entirely off this: unit cost $22.00 against list $58.00 is a 62.1% margin, a 20% floor puts the lowest workable price at $27.50, and a 15% bulk discount at $49.30 still returns 55.4%. Customer Service reads the same row so the quoted number matches what Accounting cleared.

### Tool 9: `log_payment`
- **Tables Read/Written:** payments
- **Tickets Unlocked:** 101, 102
- **Purpose:** Writes the payment row after a human approves. Agents never call this on their own initiative — it runs behind `POST /approve-payment`, which is the only path that touches `cash_accounts`.

### Tool 10: `get_desk_today`
- **Tables Read:** desk
- **Tickets Unlocked:** 101, 102
- **Purpose:** Returns `desk.date_today`, the shop's current date (2026-08-31). Added after a live run exposed the gap: Facilities reported *"the tools available here do not expose Desk.date_today, so I can't confirm today's date"* and could not say whether rent was overdue. Without it an agent either guesses the date or refuses to judge urgency, and the shop's whole overdue rule depends on it.

### Transport and how the backend uses it

`mcp_server/server.py` speaks the MCP stdio transport (JSON-RPC 2.0, protocol `2024-11-05`) and is registered in `.mcp.json` as `campus_customs`. It implements `initialize`, `tools/list`, `tools/call` and `ping` directly against the wire protocol, so it runs with no third-party dependencies.

**The FastAPI backend is a real MCP client.** `backend/mcp_client.py` spawns the server as a subprocess and performs an `initialize` handshake, and every fact an agent states is fetched with an actual `tools/call` round trip — the backend never reads those tables with its own SQL. A `ToolRecorder` collects the calls made during each agent step, so the `tools_used` list written to the audit trail is a record of calls that happened rather than a label someone typed.

This is verifiable rather than asserted. Break `mcp_server/server.py` and `POST /run-ticket/{id}` returns **503** with a message naming the command to start the server; it cannot produce agent output without it. `GET /health` and `GET /tickets` keep working, which is correct — those are plain board reads, not agent findings.

`POST /approve-payment` writes its payment row through the `log_payment` tool over the same transport, so all ten tools are exercised by a full three-ticket run. If the balance update that follows fails, the payment row is removed so `payments` can never disagree with `cash_accounts`.

### Two bugs this surfaced

- **`get_pricing` reported markup as margin.** It divided by unit cost instead of list price, so a $22.00/$58.00 item came back as `163.6%`. True margin is `62.1%`. An agent treating that as margin would approve a far deeper discount than the shop can afford. Fixed, with `markup_percent` now returned separately.
- **The bulk discount ignored the margin floor.** Accounting stated a 20% floor and then applied a flat 15% discount regardless. At a $40.00 unit cost the floor is $50.00 and the discount landed at $49.30 — below the rule it had just quoted. The discount is now clamped to the floor, and when cost rises far enough that even list price cannot clear 20%, Accounting quotes nothing and Customer Service withholds the draft entirely.

---


---

## Agent-to-MCP Tool Mapping

### Boss Agent Tools
| Tool | Table(s) Read | Purpose |
|------|---------------|---------|
| `get_tickets` | tickets | Retrieve all open tickets for triage and routing |
| `delegate_task` | tickets | Assign ticket to appropriate agent; coordinate handoff |
| `close_ticket` | tickets | Mark ticket as resolved after all dependencies met |

### Inventory Agent Tools
| Tool | Table(s) Read | Purpose |
|------|---------------|---------|
| `get_inventory_stock` | inventory | Check qty by SKU + size; trigger shortfall detection (Tickets 101, 103) |
| `get_vendors` | vendors | Identify which vendor can restock (specialty, lead_days) |
| `get_vendor_pricing` | pricing, vendors | Calculate margins and restock feasibility |
| `get_open_invoices_for_vendor` | invoices | Check if vendor has payment gate (unpaid invoices block new orders) |

### Accounting Agent Tools
| Tool | Table(s) Read | Purpose |
|------|---------------|---------|
| `get_cash_balance` | cash_accounts | Monitor checking account; prevent negative balance |
| `get_open_invoices_for_vendor` | invoices | Track vendor payables and due dates |
| `get_pricing` | pricing | Validate margins and pricing decisions |
| `approve_payment` | invoices, cash_accounts | Present payment options to human for approval |
| `log_payment` | payments | Record human-approved payments; update payments table |

### Facilities Agent Tools
| Tool | Table(s) Read | Purpose |
|------|---------------|---------|
| `get_lease_details` | leases | Retrieve rent amount and due date (Ticket 102) |
| `get_all_leases` | leases | Monitor all properties and upcoming payments |

### Customer Service Agent Tools
| Tool | Table(s) Read | Purpose |
|------|---------------|---------|
| `get_pricing` | pricing | Provide accurate prices in customer responses |
| `draft_customer_response` | tickets, inventory | Compose replies; coordinate with other agents for accuracy |

---

## The Agent Team (Pydantic AI)

Five agents built with **Pydantic AI**, all running on **`gpt-6-luna`**. Code in
`backend/agents.py`; instructions in `backend/prompts/`, one markdown file per agent.

| Agent | Owns | Delegates to |
| --- | --- | --- |
| **Boss** | Reads every ticket first, routes the work, makes the final call | Anyone |
| **Inventory** | Stock counts, vendors, lead times, restock feasibility | Anyone |
| **Accounting** | Cash, invoices, margins, prepares payments | Anyone |
| **Facilities** | Leases, rent, the shop space | Anyone |
| **Customer Service** | Drafts what the customer reads | Anyone |

### Full connectivity

Every agent carries an `ask_teammate(agent_name, question)` tool listing all five names,
so any agent can ask any other for help. This is not Boss-only fan-out: a recorded run has
**Inventory → Accounting**, where Inventory hit the vendor's unpaid invoice and handed the
money question straight to Accounting rather than bouncing back through the Boss. Every
delegation is written to the audit trail with a `delegated_by` field.

Delegation depth is capped at 2 so the team cannot loop, and a run is capped at 30 model
requests to keep a ticket inside the token budget.

### The Boss reads first

Per the shop's own rules the Boss reads the board before it routes anything. This is
enforced structurally, not just asked for in the prompt: `ask_teammate` refuses for the
Boss until `get_tickets` has been called, and tells it to read the board first.

### Agents cannot move money

`log_payment` is **not registered on any agent** (agents get the other nine). The team can only propose. The payment
row is written by `POST /approve-payment` after a human clicks approve, and that route
calls `log_payment` over the same MCP transport.

### Proposed amounts are verified before a human sees them

`backend/agent_runner.py` takes the Boss's structured `TicketResolution`, re-reads the
named invoice or lease through MCP, and uses the **database** figure. If the model's
number disagreed, the approval records `amount_corrected: true`. A hallucinated figure
cannot reach the cash path, and an amount larger than the balance is refused outright.

### Degraded mode

If `OPENAI_API_KEY` is absent or the model cannot be reached, the backend writes a
`Model unavailable` event to the audit trail and falls back to a deterministic path that
still calls every MCP tool. The `/run-ticket` response reports which engine ran
(`pydantic-ai`, `deterministic-fallback`, or `deterministic`), so a reader can always tell.

---

## Safety Guardrails & Compliance

### Token & Cost Limits
- **Per-Run Limit:** $1–$2 USD equivalent per complete ticket resolution
- **Model Used:** gpt-luna-6 only (Portkey API, professor's budget)
- **Monitoring:** Track token usage per agent per ticket; fail gracefully if overage detected
- **Approach:** Use concise prompts, avoid redundant queries, cache shared data

### Data Privacy & Security
- **No Biometric Data:** Agents never process fingerprints, facial data, or health info
- **No Government IDs:** Do not expose passport numbers, SSNs, driver's license numbers
- **No Financial Details in Logs:** Credit card numbers, bank account numbers, account routing info must never appear in audit_trail.json or any output file
- **No Sensitive Customer Info:** Do not log customer address, phone number, email, or other PII in audit trail unless absolutely required for ticket resolution
- **Identity Privacy:** Redact or exclude personally identifying info in all agent communications and logs

### Agent Authorization & Limits
- **All Payments Require Human Approval:** Agents prepare options for human review, never auto-approve
- **No Vendor Contact:** Agents never compose emails or calls to vendors—all work stays on internal board
- **No Customer Contact:** Agents never send messages to customers—only draft internal responses for board review
- **No Database Writes Except Payments & Audit:** Agents can only insert into `payments` table (via `log_payment`) and `audit_trail.json`; no other writes

### Audit Trail Logging
- **File:** `output/audit_trail.json`
- **Append Only:** Each agent action appends a new event; never wipe the file
- **Event Format:**
  ```json
  {
    "timestamp": "2026-08-31T14:00:00Z",
    "agent": "inventory",
    "action": "check_stock",
    "ticket_id": 101,
    "input_data": {"sku": "CC-TEE-WHITE", "size": "S"},
    "output_data": {"qty": 0, "found": true},
    "status": "success",
    "notes": "Out of stock; escalating to accounting for restock approval"
  }
  ```
- **Sensitive Data Rule:** Never log payment amounts > $1000 or customer personal data in output_data

---


---

## Backend API Routes

All routes served from `http://localhost:8000`

### Health Check
- **GET `/health`** — Service health status (200 if running)

### Ticket Management
- **GET `/tickets`** — Return all three tickets (101, 102, 103) with open/resolved status
- **POST `/run-ticket/{ticket_id}`** — Run the agent team on one ticket. Returns the agent events and any `pending_approval` the team prepared. Tickets needing no payment are resolved here; the rest stay open until the payment clears

### Agent Activity
- **GET `/agent-events`** — Return audit trail events: what each agent did, tools used, results (dashboard refreshes using this)

### Payment Processing
- **GET `/cash-balance`** — Return current balance from cash_accounts (checking account)
- **POST `/approve-payment`** — Release a prepared payment. Writes the `payments` row, decrements `cash_accounts`, marks a vendor invoice `paid`, and resolves the linked ticket. **The only route that changes cash.** Refuses with a 400 rather than overdrawing

### Database Management
- **POST `/reset-db`** — Restore the working database from the pristine `campus_customs.db`; writes a `Reset board` marker to the audit trail rather than erasing it, since the trail is append-only

---


## The Dashboard

`frontend/` — React + Vite + TypeScript, served at `http://localhost:5173`, talking to the
backend at `http://localhost:8000` (that origin is allowed by the CORS middleware in
`backend/main.py`).

### Layout

Three columns, matching how the work actually flows:

| Column | Shows |
| --- | --- |
| **Left — The team** | All five agents. Each stays dim until the ticket actually routes to it, so a rent ticket visibly leaves Inventory and Customer Service grey. The status dot reads idle, queued, working or done |
| **Middle — Tickets** | A dense table of all three tickets (id, type, subject, requester, item, qty, opened, status). Selecting a row opens a detail panel with the SKU facts and a summary of what each agent did |
| **Right — Activity** | The run as a timeline: each agent's action, the full sentence it produced, and the MCP tools it called shown as chips. The payment approval card pins to the bottom |

### What it does

- Lists all three tickets and their open/resolved status (`GET /tickets`)
- Runs the agent team on a selected ticket (`POST /run-ticket/{id}`)
- Shows each agent's action and output as the run unfolds — the content is exactly what the
  backend returned in one response; only the ~700ms pacing between steps is client-side
- Marks a ticket resolved when the run finishes, or when its payment clears
- Summarises what each agent contributed, per ticket
- **Show email draft** expands the full message Customer Service wrote, held internally
- **Show the math** expands Accounting's working: the invoice, the balance, the margin
  calculation, the discount floor
- Lets a human approve a prepared payment (`POST /approve-payment`), after which the checking
  balance in the top bar drops and briefly flashes
- **Reset board** restores the pristine database for a fresh run (`POST /reset-db`)

If the backend is unreachable the board says so and names the command to start it. It never
falls back to sample data.

Visual rationale is in `output/design.md`.

---

## Verified Full Run

One clean run of all three tickets, starting from a reset working database.

| | |
| --- | --- |
| Shop date | 2026-08-31 |
| Starting checking balance | **$3,400.00** |
| Ticket 101 | Resolved — vendor payment, invoice 501, −$840.00 → $2,560.00 |
| Ticket 102 | Resolved — rent payment, lease 1, −$2,400.00 → $160.00 |
| Ticket 103 | Resolved — quote only, no cash → $160.00 |
| Ending checking balance | **$160.00** |
| Human approvals required | 2 |

`$3,400.00 − $840.00 − $2,400.00 = $160.00`, which matches `cash_accounts.balance` and the two
rows in `payments`.

Routing matched the plan on all three tickets. Tools matched on 101 and 102. On 103,
`get_open_invoices_for_vendor` was missing from the first implementation and was added — it
matters because the hoodie restock comes from the same vendor holding invoice 501, so without
it the agent would promise a lead time it could not honour.

Full detail: `output/desk_tickets.html` (expected vs. actual, cash ledger, reflection),
`output/resolved_tickets.json`, `output/resolved_board.html`, `output/audit_trail.json`.
